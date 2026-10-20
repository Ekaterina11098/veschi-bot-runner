"""China FBS -> customer order -> demand -> full sales return.
Secrets stay in the runner. Operational configuration/state stays in Supabase.
No live writes until writes_enabled is explicitly enabled after verification.
"""
import argparse
import collections
import datetime as dt
import gzip
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

MS = "https://api.moysklad.ru/api/remap/1.2/"
WB = "https://marketplace-api.wildberries.ru/"
CONFIG = "fbs_document_chain:china:config:v1"
STATE = "fbs_document_chain:china:state:v1"
PREFIX = "fbs_document_chain:china:supply:v1:"
TYPES = ("customerorder", "demand", "salesreturn")


class Stop(RuntimeError):
    pass


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def stamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def href(value):
    return value.get("meta", {}).get("href", "")


def meta(value):
    return {"meta": {k: value["meta"][k] for k in ("href", "type", "mediaType")}}


class Transport:
    def __init__(self):
        self.last = 0

    def request(self, base, path, method="GET", body=None, params=None):
        if base not in (MS, WB, os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/"):
            raise Stop("Unexpected API destination")
        if base == WB and method != "GET":
            raise Stop("WB writes are prohibited")
        if path.startswith(("http:", "https:")):
            raise Stop("Absolute API path prohibited")
        token = os.environ["MOYSKLAD_API_TOKEN"] if base == MS else (
            os.environ["WB_TOKEN_3"] if base == WB else os.environ["SUPABASE_SECRET_KEY"])
        headers = {"Accept": "application/json;charset=utf-8", "Content-Type": "application/json",
                   "Accept-Encoding": "gzip", "Authorization": ("Bearer " if base != WB else "") + token}
        if base not in (MS, WB):
            headers.update(apikey=token, Prefer="resolution=merge-duplicates,return=representation")
        url = base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        time.sleep(max(0, .3 - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            # Never log response bodies, token values, or authenticated URLs.
            raise Stop("HTTP_" + str(error.code) + " " + method + " " + path.split("?")[0]) from None
        except (TimeoutError, urllib.error.URLError):
            raise Stop("API transport outcome uncertain") from None


class Cache:
    def __init__(self, transport):
        self.t = transport
        self.base = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/"

    def get(self, key):
        rows = self.t.request(self.base, "telegram_api_cache", params={
            "cache_key": "eq." + key, "select": "payload"})
        if len(rows) > 1:
            raise Stop("Duplicate state key")
        return rows[0]["payload"] if rows else None

    def put(self, key, payload):
        self.t.request(self.base, "telegram_api_cache", "POST", {
            "cache_key": key, "payload": payload, "expires_at": "2036-10-20T00:00:00Z",
            "updated_at": now()}, {"on_conflict": "cache_key"})
        if self.get(key) != payload:
            raise Stop("State readback mismatch")

    def pending(self):
        rows = self.t.request(self.base, "telegram_api_cache", params={
            "cache_key": "like." + PREFIX + "*", "select": "cache_key,payload",
            "limit": 1000, "payload->>status": "neq.complete"})
        if len(rows) >= 1000:
            raise Stop("Pending state list incomplete")
        return [x for x in rows if x["payload"].get("status") != "complete"]


class Worker:
    def __init__(self, transport, cache, config):
        self.t, self.db, self.c = transport, cache, config

    def ms_rows(self, path, params=None):
        rows, offset = [], 0
        while True:
            data = self.t.request(MS, path, params={**(params or {}), "limit": 1000, "offset": offset})
            batch = data.get("rows")
            if not isinstance(batch, list) or not isinstance(data.get("meta", {}).get("size"), int):
                raise Stop("Incomplete MoySklad collection")
            rows += batch
            if len(rows) == data["meta"]["size"]:
                return rows
            if not batch or len(rows) > 20000 or len(rows) > data["meta"]["size"]:
                raise Stop("MoySklad pagination incomplete")
            offset += len(batch)

    def supplies(self):
        result, cursor, visited = [], 0, set()
        while True:
            if cursor in visited:
                raise Stop("WB pagination did not advance")
            visited.add(cursor)
            page = self.t.request(WB, "api/v3/supplies", params={"limit": 1000, "next": cursor})
            batch = page.get("supplies")
            if not isinstance(batch, list) or "next" not in page:
                raise Stop("WB supplies incomplete")
            result += batch
            if not batch or not page["next"]:
                break
            cursor = page["next"]
            if len(result) > 100000:
                raise Stop("WB supply scope exceeds limit")
        ids = [s["id"] for s in result]
        if len(ids) != len(set(ids)):
            raise Stop("Duplicate WB supply IDs")
        return result

    def positions(self, supply):
        ident = supply["id"]
        answer = self.t.request(WB, "api/marketplace/v3/supplies/" + ident + "/order-ids")
        ids = answer.get("orderIds")
        if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
            raise Stop("Supply order identities missing or duplicated")
        end = dt.datetime.now(dt.timezone.utc)
        begin = end - dt.timedelta(days=30) + dt.timedelta(seconds=1)
        if stamp(supply["closedAt"]) > end:
            raise Stop("Supply requires wider historical order retrieval")
        found, cursor, visited = {}, 0, set()
        wanted = set(ids)
        while True:
            if cursor in visited:
                raise Stop("WB order pagination did not advance")
            visited.add(cursor)
            page = self.t.request(WB, "api/v3/orders", params={
                "limit": 1000, "next": cursor,
                "dateFrom": int(begin.timestamp()), "dateTo": int(end.timestamp())})
            batch = page.get("orders")
            if not isinstance(batch, list) or "next" not in page:
                raise Stop("WB order list incomplete")
            for order in batch:
                if order.get("id") in wanted:
                    if order["id"] in found and found[order["id"]] != order:
                        raise Stop("Conflicting WB order")
                    found[order["id"]] = order
            if set(found) == wanted:
                break
            if not batch or not page["next"]:
                self.db.put("fbs_document_chain:china:order_lookup_diagnostic:v1", {"at": now(), "supply": supply, "expected": len(ids), "found": len(found), "missing": sorted(wanted-set(found)), "dateFrom": begin.isoformat(), "dateTo": end.isoformat()})
                raise Stop("Not all supply orders found")
            cursor = page["next"]
        counts = collections.Counter()
        for order in found.values():
            article = order.get("article")
            if not isinstance(article, str) or not article.strip():
                raise Stop("WB article missing")
            counts[article.strip()] += 1
        positions = []
        for article, quantity in sorted(counts.items()):
            products = self.ms_rows("entity/product", {"filter": "article=" + article})
            products = [p for p in products if p.get("article", "").strip() == article and not p.get("archived")]
            if len(products) != 1 or products[0].get("variantsCount", 0):
                raise Stop("Product article missing, duplicated or has variants: " + article)
            product = products[0]
            if product.get("isSerialTrackable") or product.get("trackingType", "NOT_TRACKED") != "NOT_TRACKED":
                raise Stop("Product requires marking/serial setup: " + article)
            positions.append({"quantity": quantity, "price": 0, "discount": 0, "vat": 0,
                              "vatEnabled": False, "assortment": meta(product)})
        if len(positions) > 1000:
            raise Stop("Document exceeds configured position limit")
        return positions, sorted(ids)

    def verify(self, typ, doc, payload):
        for key in ("organization", "agent", "store"):
            if href(doc.get(key, {})) != href(payload[key]):
                raise Stop("Document " + key + " mismatch")
        if doc.get("applicable") is not True or doc.get("sum") != 0:
            raise Stop("Document not posted or nonzero")
        for link in ("customerOrder", "demand"):
            if link in payload and href(doc.get(link, {})) != href(payload[link]):
                raise Stop("Document link mismatch")
        positions = self.ms_rows("entity/" + typ + "/" + doc["id"] + "/positions")
        def totals(values):
            result = collections.Counter()
            for p in values:
                if p.get("price") != 0 or p.get("quantity", 0) <= 0:
                    raise Stop("Nonzero price or invalid quantity")
                result[href(p["assortment"])] += p["quantity"]
            return result
        if totals(positions) != totals(payload["positions"]):
            raise Stop("Document positions mismatch")

    def ensure(self, typ, payload, state, key):
        ext = "fbs-china:" + state["supply"]["id"] + ":" + typ
        payload = {**payload, "externalCode": ext}
        docs = self.ms_rows("entity/" + typ, {"filter": "externalCode=" + ext})
        if len(docs) > 1:
            raise Stop("Duplicate document external code")
        if docs:
            doc = docs[0]
        elif state.get("inflight"):
            raise Stop("Uncertain prior document creation; manual reconciliation required")
        else:
            # Check for manually entered supply numbers before creating any document.
            if typ == "customerorder" and self.ms_rows("entity/customerorder", {"filter": "name=" + state["supply"]["id"]}):
                raise Stop("Existing manual order for this supply; reconcile before continuing")
            state["inflight"] = typ
            state["status"] = "creating_" + typ
            self.db.put(key, state)
            self.t.request(MS, "entity/" + typ, "POST", payload)
            docs = self.ms_rows("entity/" + typ, {"filter": "externalCode=" + ext})
            if len(docs) != 1:
                raise Stop("Created document readback ambiguous")
            doc = docs[0]
        self.verify(typ, doc, payload)
        state.setdefault("documents", {})[typ] = {"id": doc["id"], "name": doc["name"], **meta(doc)}
        if state.get("inflight") == typ:
            state.pop("inflight", None)
        state["status"] = typ + "_verified"
        self.db.put(key, state)
        return meta(doc)

    def process(self, state):
        supply = state["supply"]
        key = PREFIX + supply["id"]
        if "positions" not in state:
            state["positions"], state["order_ids"] = self.positions(supply)
            state["status"] = "prepared"
            self.db.put(key, state)
        current = self.t.request(WB, "api/v3/supplies/" + supply["id"])
        current_ids = self.t.request(WB, "api/marketplace/v3/supplies/" + supply["id"] + "/order-ids").get("orderIds", [])
        if current.get("done") is not True or sorted(current_ids) != state["order_ids"]:
            raise Stop("Supply composition/status changed")
        links = {}
        for typ in TYPES:
            payload = json.loads(json.dumps(self.c["templates"][typ]))
            payload.update(positions=state["positions"], applicable=True,
                           description="WB FBS China " + supply["id"] + " / " + supply.get("name", ""),
                           moment=stamp(supply["closedAt"]).astimezone(dt.timezone(dt.timedelta(hours=3))).strftime("%Y-%m-%d %H:%M:%S"))
            if typ == "customerorder":
                payload["name"] = supply["id"]
            elif typ == "demand":
                payload["customerOrder"] = links["customerorder"]
            else:
                payload["demand"] = links["demand"]
            links[typ] = self.ensure(typ, payload, state, key)
        state.update(status="complete", completed_at=now())
        state.pop("error", None)
        self.db.put(key, state)

    def run(self, mode):
        if mode == "status":
            return {"status": self.c["status"], "writes_enabled": self.c["writes_enabled"],
                    "baseline_exists": self.db.get(STATE) is not None}
        if mode not in ("bootstrap", "preview", "run"):
            raise Stop("Unknown mode")
        if mode == "run" and (not self.c.get("writes_enabled") or self.c.get("status") != "active"):
            return {"status": "configured_waiting_for_verification", "writes": 0}
        if self.c.get("scope_confirmed") is not True:
            raise Stop("Organization/counterparty scope needs confirmation")
        state = self.db.get(STATE)
        if mode == "bootstrap" and state:
            raise Stop("Baseline already exists; reset prohibited")
        if mode == "run" and not state:
            raise Stop("Activate baseline before execution")
        start = now()
        supplies = self.supplies()
        if mode == "bootstrap":
            self.db.put(STATE, {"activated_at": start, "baseline_done_ids":
                sorted(s["id"] for s in supplies if s.get("done") is True and s.get("closedAt") and stamp(s["closedAt"]) <= stamp(start)), "created_at": now()})
            return {"status": "baseline_created", "writes": 0}
        if mode == "preview":
            # Does not change the activation boundary or create operational documents.
            sample = sorted((s for s in supplies if s.get("done") and s.get("closedAt")),
                            key=lambda s: s["closedAt"], reverse=True)[:1]
            result = []
            for supply in sample:
                positions, ids = self.positions(supply)
                result.append({"supply_id": supply["id"], "orders": len(ids), "positions": len(positions),
                               "quantity": sum(p["quantity"] for p in positions), "zero_prices": True})
            self.db.put("fbs_document_chain:china:preview:v1", {"observed_at": now(), "result": result, "writes": 0})
            return {"status": "preview_saved", "writes": 0}
        old = set(state["baseline_done_ids"])
        candidates = {r["payload"]["supply"]["id"]: r["payload"] for r in self.db.pending()}
        for supply in supplies:
            if not supply.get("done") or supply["id"] in old or not supply.get("closedAt"):
                continue
            if stamp(supply["closedAt"]) <= stamp(state["activated_at"]):
                continue
            key = PREFIX + supply["id"]
            previous = self.db.get(key)
            if previous and previous.get("status") == "complete":
                continue
            candidates[supply["id"]] = previous or {"supply": supply, "status": "discovered", "discovered_at": now()}
        errors, completed = [], 0
        for supply_id, item in sorted(candidates.items()):
            try:
                self.process(item)
                completed += 1
            except Exception as exc:
                # Persist the inflight marker when the write result is uncertain.
                item["error"] = str(exc) if isinstance(exc, Stop) else type(exc).__name__
                item["last_error_at"] = now()
                self.db.put(PREFIX + supply_id, item)
                errors.append({"supply_id": supply_id, "error": item["error"]})
        self.db.put("fbs_document_chain:china:last_run:v1", {"at": now(), "completed": completed, "errors": errors})
        if errors:
            raise Stop("One or more supply chains require attention; see private run journal")
        return {"status": "done", "completed": completed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["status", "preview", "bootstrap", "run"], default="status")
    args = parser.parse_args()
    transport = Transport()
    cache = Cache(transport)
    config = cache.get(CONFIG)
    if not config or config.get("version") != 1 or config.get("cabinet") != "token_3":
        raise Stop("China FBS configuration unavailable")
    result = Worker(transport, cache, config).run(args.mode)
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc) if isinstance(exc, Stop) else type(exc).__name__}))
        raise SystemExit(1)
