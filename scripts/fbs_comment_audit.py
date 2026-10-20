"""Continuously reconcile comments on ledger-owned, completed FBS chains only."""
import argparse
import json
from fbs_document_chain import Cache, Transport, Worker, Stop, MS, TYPES, href, now

ROOT = "fbs_document_chain:"
CURSOR = ROOT + "comment_audit:cursor:v1"
REPORT = ROOT + "comment_audit:last_run:v1"
CABINETS = ("china", "ip", "ooo", "ozon")


def audit_chain(t, db, cabinet, state):
    config = db.get(ROOT + cabinet + ":config:v1")
    expected = state.get("order_annotation", {}).get("description")
    if not config or not config.get("order_annotation") or not expected:
        raise Stop("Expected comment/config unavailable")
    w = Worker(t, db, config)
    docs = {typ: t.request(MS, "entity/" + typ + "/" + state["documents"][typ]["id"]) for typ in TYPES}
    payloads = {}
    for typ in TYPES:
        payload = dict(config["templates"][typ], positions=state["positions"], description=docs[typ].get("description"))
        if typ == "demand":
            payload["customerOrder"] = state["documents"]["customerorder"]
        elif typ == "salesreturn":
            payload["demand"] = state["documents"]["demand"]
        # Validate stock scope, posting and links before any comment write.
        w.verify(typ, docs[typ], payload)
        payload["description"] = expected
        payloads[typ] = payload
    repaired = []
    for typ in TYPES:
        path = "entity/" + typ + "/" + docs[typ]["id"]
        if docs[typ].get("description") != expected:
            # PUT is partial: no positions, posting flag, date, status or price fields.
            t.request(MS, path, "PUT", {"description": expected})
            repaired.append(typ)
        after = t.request(MS, path)
        w.verify(typ, after, payloads[typ])
    return {"supply_id": state["supply"]["id"], "cabinet": cabinet,
            "documents_verified": 3, "repaired": repaired}


def run(full=False):
    t = Transport()
    db = Cache(t)
    cursors = {} if full else (db.get(CURSOR) or {}).get("cursors", {})
    report = {"at": now(), "status": "running", "chains": [], "errors": []}
    for cabinet in CABINETS:
        prefix = ROOT + cabinet + ":supply:v1:"
        cursor = cursors.get(cabinet)
        while True:
            # Indexed primary-key range; do not scan JSON across the shared cache.
            lower = "cache_key.gt." + cursor if cursor else "cache_key.gte." + prefix
            params = {"select": "cache_key,payload", "order": "cache_key.asc", "limit": 10,
                      "and": "(" + lower + ",cache_key.lt." + prefix + "~)"}
            rows = t.request(db.base, "telegram_api_cache", params=params)
            for row in rows:
                key, state = row["cache_key"], row["payload"]
                if state.get("status") == "complete":
                    try:
                        report["chains"].append(audit_chain(t, db, cabinet, state))
                    except Exception as exc:
                        report["errors"].append({"key": key, "error": str(exc) if isinstance(exc, Stop) else type(exc).__name__})
                cursor = key
                db.put(REPORT, report)
            cursors[cabinet] = cursor if len(rows) == 10 else None
            db.put(CURSOR, {"cursors": cursors, "at": now()})
            if not full or len(rows) < 10:
                break
    report.update(status="failed" if report["errors"] else "verified", completed_at=now())
    db.put(REPORT, report)
    print(json.dumps({"status": report["status"], "chains": len(report["chains"]),
                      "documents": sum(x["documents_verified"] for x in report["chains"]),
                      "repaired": sum(len(x["repaired"]) for x in report["chains"]),
                      "errors": len(report["errors"])}))
    if report["errors"]:
        raise Stop("Comment audit requires attention; see private journal")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    run(args.all)
