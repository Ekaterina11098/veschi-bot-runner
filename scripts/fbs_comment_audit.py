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
    cursor = None if full else (db.get(CURSOR) or {}).get("last_key")
    report = {"at": now(), "status": "running", "chains": [], "errors": []}
    configs = ",".join("cache_key.like." + ROOT + cabinet + ":supply:v1:*" for cabinet in CABINETS)
    while True:
        params = {"select": "cache_key,payload", "or": "(" + configs + ")",
                  "payload->>status": "eq.complete", "order": "cache_key.asc", "limit": 10}
        if cursor:
            params["cache_key"] = "gt." + cursor
        rows = t.request(db.base, "telegram_api_cache", params=params)
        if not rows:
            db.put(CURSOR, {"last_key": None, "at": now()})
            break
        for row in rows:
            key, state = row["cache_key"], row["payload"]
            cabinet = key.split(":")[1]
            try:
                result = audit_chain(t, db, cabinet, state)
                report["chains"].append(result)
            except Exception as exc:
                report["errors"].append({"key": key, "error": str(exc) if isinstance(exc, Stop) else type(exc).__name__})
            cursor = key
            db.put(REPORT, report)
        db.put(CURSOR, {"last_key": cursor if len(rows) == 10 else None, "at": now()})
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
