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


def excluded_from_picking(status):
    # complete records the seller's delivery handover. A later buyer refusal
    # does not undo the physical shipment or its picking-list quantity.
    if status.get("supplierStatus") == "complete":
        return False
    return status.get("supplierStatus") == "cancel" or status.get("wbStatus") in ("canceled", "canceled_by_client")


def href(value):
    return value.get("meta", {}).get("href", "")


def meta(value):
    return {"meta": {k: value["meta"][k] for k in ("href", "type", "mediaType")}}


class Transport:
    def __init__(self):
        self.last = 0

    def request(self, base, path, method="GET", body=None, params=None):
        # Reads can be retried safely; an uncertain write must be reconciled by ensure().
        for attempt in range(3):
            try:
                return self._request_once(base, path, method, body, params)
            except Stop as error:
                message = str(error)
                transient = message == "API transport outcome uncertain" or any(
                    message.startswith("HTTP_" + str(code) + " ")
                    for code in (429, 500, 502, 503, 504))
                if method != "GET" or not transient or attempt == 2:
                    raise
                delay = 2 * (attempt + 1)
                print(json.dumps({"event": "safe_read_retry",
                                  "attempt": attempt + 2, "delay_seconds": delay}))
                time.sleep(delay)

    def insert_cache_once(self, body):
        return self._request_once(
            os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/",
            "telegram_api_cache", "POST", body, {"on_conflict": "cache_key"},
            cache_prefer="resolution=ignore-duplicates,return=representation")

    def _request_once(self, base, path, method="GET", body=None, params=None, cache_prefer=None):
        if base not in (MS, WB, os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/"):
            raise Stop("Unexpected API destination")
        if base == WB and method != "GET" and not (method == "POST" and path == "api/v3/orders/status"):
            raise Stop("WB writes are prohibited")
        if path.startswith(("http:", "https:")):
            raise Stop("Absolute API path prohibited")
        token = os.environ["MOYSKLAD_API_TOKEN"] if base == MS else (
            os.environ["WB_TOKEN_3"] if base == WB else os.environ["SUPABASE_SECRET_KEY"])
        headers = {"Accept": "application/json;charset=utf-8", "Content-Type": "application/json",
                   "Accept-Encoding": "gzip", "Authorization": ("Bearer " if base != WB else "") + token}
        if base not in (MS, WB):
            headers.update(apikey=token, Prefer=cache_prefer or "resolution=merge-duplicates,return=representation")
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

    def claim(self, key, payload):
        # INSERT ... ON CONFLICT DO NOTHING is atomic across overlapping runners.
        key = self.scope(key) if hasattr(self, "scope") else key
        receipt = {**payload, "claim_nonce": str(uuid.uuid4())}
        body = {"cache_key": key, "payload": receipt,
                "expires_at": "2036-10-20T00:00:00Z", "updated_at": now()}
        try:
            inserted = self.t.insert_cache_once(body)
            return bool(inserted)
        except Stop:
            # Reconcile an uncertain insert; never blindly replay the claim.
            return Cache.get(self, key) == receipt


class Worker:
    def __init__(self, transport, cache, config):
        self.t, self.db, self.c = transport, cache, config

    def execution_permission(self, direct=False):
        policy = self.c.get("execution_policy")
        if not policy or getattr(self, "_execution_permit", None):
            return None
        current = stamp(now())
        local = current.astimezone(dt.timezone(dt.timedelta(hours=3)))
        kind = "manual" if direct else os.environ.get("FBS_EXECUTION_KIND", "manual")
        approval_id = os.environ.get("FBS_OWNER_APPROVAL_ID", "").strip()
        cabinet = self.c["cabinet"]
        def wait(status, reason):
            result = {"status": status, "writes": 0, "at": now(), "reason": reason,
                      "cabinet": cabinet, "daily_time": "19:00", "timezone": "Europe/Moscow"}
            self.db.put("fbs_document_chain:china:execution_gate:v1", result)
            if kind == "manual":
                self.db.put("fbs_document_chain:china:owner_approval_request:v1", {
                    **result, "owner_confirmation_required": True,
                    "message": "Внеплановое списание в МоемСкладе: требуется подтверждение владельца и точный список поставок."})
            return result
        if kind == "manual":
            approval = self.db.get("fbs_document_chain:china:owner_approval:v1:" + approval_id) if approval_id else None
            try:
                valid = (approval and approval.get("owner_confirmed") is True
                         and approval.get("cabinet") == cabinet
                         and stamp(approval["expires_at"]) > current
                         and isinstance(approval.get("supply_ids"), list)
                         and bool(approval["supply_ids"]))
            except (KeyError, TypeError, ValueError):
                valid = False
            if not valid:
                return wait("owner_approval_required", "Внеплановое списание запрещено без разового подтверждения владельца.")
            if not self.db.claim("fbs_document_chain:china:owner_approval_used:v1:" + approval_id,
                                 {"at": now(), "cabinet": cabinet, "approval_id": approval_id}):
                return wait("owner_approval_already_used", "Разовое подтверждение уже использовано.")
            self._execution_permit = {"kind": "manual", "supply_ids": set(approval["supply_ids"])}
            return None
        if kind not in ("daily", "poll") or local.hour != 19:
            return wait("waiting_for_daily_time", "Автоматические списания выполняются один раз в день в 19:00 МСК.")
        day = local.date().isoformat()
        if not self.db.claim("fbs_document_chain:china:daily_execution:v1:" + day,
                             {"at": now(), "cabinet": cabinet, "local_date": day,
                              "github_run_id": os.environ.get("GITHUB_RUN_ID")}):
            return wait("daily_run_already_claimed", "Ежедневный запуск уже был начат; повтор требует подтверждения владельца.")
        self._execution_permit = {"kind": "daily", "local_date": day}
        return None

    def require_execution_permission(self, supply_id):
        decision = self.execution_permission(direct=True)
        if decision:
            raise Stop(decision["reason"])
        permit = getattr(self, "_execution_permit", {})
        if permit.get("kind") == "manual" and supply_id not in permit["supply_ids"]:
            raise Stop("Supply is outside the owner's one-time confirmation")

    def require_available_stock(self, payload, state):
        if not self.c.get("execution_policy", {}).get("forbid_negative_stock"):
            return
        needed = collections.Counter()
        for p in payload["positions"]:
            needed[href(p["assortment"]).split("?")[0]] += p["quantity"]
        stocks = self.ms_rows("report/stock/all", {"filter": "store=" + href(payload["store"]),
            "stockMode": "all", "quantityMode": "all"})
        by_id = {href(row).split("?")[0]: row for row in stocks}
        shortages = []
        for product, quantity in needed.items():
            stock = by_id.get(product, {})
            if stock.get("stock", 0) < quantity or stock.get("quantity", 0) < quantity:
                shortages.append({"product_href": product, "article": stock.get("article"),
                    "needed": quantity, "stock": stock.get("stock", 0), "available": stock.get("quantity", 0)})
        if shortages:
            state["stock_shortages"] = shortages
            self.db.put("fbs_document_chain:china:stock_approval_request:v1", {
                "at": now(), "supply_id": state["supply"]["id"],
                "shortages": shortages, "owner_confirmation_required": True,
                "message": "Недостаточно остатков. Отгрузка не проведена; требуется решение владельца."})
            raise Stop("Insufficient available stock; shipment blocked pending owner decision")

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
        statuses = {}
        for offset in range(0, len(ids), 100):
            response = self.t.request(WB, "api/v3/orders/status", method="POST", body={"orders": ids[offset:offset+100]})
            for status in response.get("orders", []):
                if status.get("id") in statuses:
                    raise Stop("Duplicate order status")
                statuses[status["id"]] = status
        if set(statuses) != set(ids):
            raise Stop("Picking-list status scope incomplete")
        cancelled = {ident for ident, status in statuses.items() if excluded_from_picking(status)}
        self.db.put("fbs_document_chain:china:picking_scope:v1:" + ident, {
            "at": now(), "supply_id": ident, "raw_count": len(ids), "picking_count": len(ids)-len(cancelled),
            "excluded": [{"id": i, "article": found[i]["article"], "status": statuses[i]} for i in sorted(cancelled)],
            "included_order_ids": sorted(set(ids)-cancelled)})
        if len(cancelled) == len(ids):
            raise Stop("Picking list has no active orders")
        counts = collections.Counter()
        for order in found.values():
            if order["id"] in cancelled:
                continue
            article = order.get("article")
            if not isinstance(article, str) or not article.strip():
                raise Stop("WB article missing")
            counts[article.strip()] += 1
        # Keep the WB source warehouse IDs for every non-cancelled order.
        # Supply names are user-editable and MUST NOT determine source storage.
        self._source_warehouse_supply_id = supply["id"]
        self._source_warehouse_ids = {oid: found[oid].get("warehouseId") for oid in ids if oid not in cancelled}
        positions = []
        if not hasattr(self, "_product_index"):
            self._product_index = {}
            for product in self.ms_rows("entity/product", {"filter": "archived=false"}):
                if not product.get("archived") and isinstance(product.get("article"), str):
                    self._product_index.setdefault(product["article"].strip().casefold(), []).append(product)
        for article, quantity in sorted(counts.items()):
            products = self._product_index.get(article.casefold(), [])
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
        if self.c.get("order_annotation") and doc.get("description") != payload.get("description"):
            raise Stop("Document comment mismatch")
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
        ext = self.c.get("document_prefix", "fbs-china") + ":" + state["supply"]["id"] + ":" + typ
        payload = {**payload, "externalCode": ext}
        docs = self.ms_rows("entity/" + typ, {"filter": "externalCode=" + ext})
        if len(docs) > 1:
            raise Stop("Duplicate document external code")
        if docs:
            doc = docs[0]
        elif state.get("inflight"):
            raise Stop("Uncertain prior document creation; manual reconciliation required")
        else:
            self.require_execution_permission(state["supply"]["id"])
            if typ == "demand":
                self.require_available_stock(payload, state)
            # Check for manually entered supply numbers before creating any document.
            if typ == "customerorder" and self.ms_rows("entity/customerorder", {"filter": "name=" + state["supply"]["id"]}):
                raise Stop("Existing manual order for this supply; reconcile before continuing")
            state["inflight"] = typ
            state["status"] = "creating_" + typ
            self.db.put(key, state)
            try:
                self.t.request(MS, "entity/" + typ, "POST", payload)
            except Stop as error:
                # Validation/auth rejection means the API did not accept creation.
                # Preserve the marker for timeouts and server errors.
                if any(str(error).startswith("HTTP_" + str(code) + " POST ")
                       for code in (400, 401, 403, 404, 405, 412, 413, 415, 422)):
                    state.pop("inflight", None)
                    state["status"] = typ + "_rejected"
                    state["last_rejection"] = {"type": typ, "error": str(error), "at": now()}
                    self.db.put(key, state)
                raise
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

    def order_annotation(self, supply):
        rule = self.c.get("order_annotation")
        if not rule:
            return None
        metadata = self.t.request(MS, "entity/customerorder/metadata")
        states = [s for s in metadata.get("states", []) if s.get("name") == rule["state_name"]]
        if len(states) != 1:
            raise Stop("Required customer order completion state missing or ambiguous")
        label = " ".join(supply.get("name", "").split())
        cabinet_word = rule.get("cabinet_word", "Китай")
        if cabinet_word != "Китай":
            label = " ".join(word for word in label.split() if word != cabinet_word)
        # ООО supply prefix К already denotes Киргизия; keep the destination once.
        if rule.get("comment_prefix") == "Киргизия" and label.startswith("К "):
            label = label[2:].strip()
        if label.endswith(" Китай"):
            label = label[:-len(" Китай")].strip()
        elif label.startswith("Китай "):
            label = label[len("Китай "):].strip()
        if not label or label == "Китай":
            raise Stop("Supply category missing for customer order comment")
        date = stamp(supply["closedAt"]).astimezone(dt.timezone(dt.timedelta(hours=3))).strftime("%d %m %y")
        return {"description": date + "  " + rule.get("comment_prefix", "Гонконг") + " " + label, "state": meta(states[0])}

    def validate_source(self, state):
        supply = state["supply"]
        current = self.t.request(WB, "api/v3/supplies/" + supply["id"])
        current_ids = self.t.request(WB, "api/marketplace/v3/supplies/" + supply["id"] + "/order-ids").get("orderIds", [])
        if current.get("done") is not True or sorted(current_ids) != state["order_ids"]:
            raise Stop("Supply composition/status changed")

    def china_warehouse_routing(self, state, key):
        """Choose the China document warehouses using WB order warehouseId, never supply name."""
        supply = state["supply"]
        if self.c.get("cabinet") != "token_3":
            return None
        local_date = stamp(supply["closedAt"]).astimezone(dt.timezone(dt.timedelta(hours=3))).date()
        if local_date < dt.date(2026, 11, 12):
            return None  # Keep historical documents and recovery unchanged.
        if getattr(self, "_source_warehouse_supply_id", None) != supply["id"]:
            # When resuming a partial chain, re-read the frozen pick list.
            positions, order_ids = self.positions(supply)
            if order_ids != state["order_ids"] or positions != state["positions"]:
                raise Stop("WB pick list drift before warehouse routing")
        origin_by_order = getattr(self, "_source_warehouse_ids", {})
        if set(origin_by_order) != set(state["order_ids"]):
            raise Stop("WB origin warehouse missing for one or more included orders")
        warehouse_ids = set(origin_by_order.values())
        if len(warehouse_ids) != 1:
            raise Stop("Mixed or unknown WB origin warehouses; manual reconciliation required")
        warehouse_id = warehouse_ids.pop()
        origin_store_by_wb_id = {
            2126188: ("3c67619d-f25d-11ee-0a80-0c6f000a027a", "МСК"),
            2308581: ("2233c6a7-d906-11f1-0a80-197e004df0d2", "Гуанджоу"),
        }
        if warehouse_id not in origin_store_by_wb_id:
            raise Stop("Unapproved WB origin warehouse ID: " + str(warehouse_id))
        origin_id, origin_name = origin_store_by_wb_id[warehouse_id]
        return_id = "c599b096-a784-11f1-0a80-15f1000f8193"
        # Confirm the configured store and live warehouse identity before making documents.
        for ident, name in ((origin_id, origin_name), (return_id, "Гонконг WB FBO")):
            live = self.t.request(MS, "entity/store/" + ident)
            if live.get("name", "").strip().casefold() != name.casefold() or live.get("archived"):
                raise Stop("MoySklad warehouse identity/active state mismatch: " + name)
        expected_return = MS + "entity/store/" + return_id
        if href(self.c["templates"]["salesreturn"]["store"]) != expected_return:
            raise Stop("China configured return warehouse differs from approved Hong Kong FBO")
        route = {"wb_warehouse_id": warehouse_id, "source_store_id": origin_id,
                 "source_store": origin_name, "return_store_id": return_id,
                 "return_store": "Гонконг WB FBO"}
        if state.get("warehouse_routing") and state["warehouse_routing"] != route:
            raise Stop("Frozen warehouse routing changed; stop to prevent wrong-stock movement")
        # Freeze routing before creation so any later re-run uses the same warehouse.
        state["warehouse_routing"] = route
        self.db.put(key, state)
        return {
            "customerorder": MS + "entity/store/" + origin_id,
            "demand": MS + "entity/store/" + origin_id,
            "salesreturn": expected_return,
        }

    def process(self, state):
        supply = state["supply"]
        self.require_execution_permission(supply["id"])
        key = PREFIX + supply["id"]
        annotation = self.order_annotation(supply)
        if "positions" not in state:
            state["positions"], state["order_ids"] = self.positions(supply)
            state["status"] = "prepared"
            self.db.put(key, state)
        self.validate_source(state)
        route = self.china_warehouse_routing(state, key)
        # Preflight the exact source warehouse before writing the first document.
        if route:
            stock_payload = json.loads(json.dumps(self.c["templates"]["demand"]))
            stock_payload["store"]["meta"]["href"] = route["demand"]
            stock_payload["positions"] = state["positions"]
            self.require_available_stock(stock_payload, state)
        links = {}
        for typ in TYPES:
            payload = json.loads(json.dumps(self.c["templates"][typ]))
            if route:
                payload["store"]["meta"]["href"] = route[typ]
            payload.update(positions=state["positions"], applicable=True,
                           description="WB FBS China " + supply["id"] + " / " + supply.get("name", ""),
                           moment=stamp(supply["closedAt"]).astimezone(dt.timezone(dt.timedelta(hours=3))).strftime("%Y-%m-%d %H:%M:%S"))
            if annotation:
                payload["description"] = annotation["description"]
            if typ == "customerorder":
                payload["name"] = supply["id"]
            elif typ == "demand":
                payload["customerOrder"] = links["customerorder"]
            else:
                payload["demand"] = links["demand"]
            links[typ] = self.ensure(typ, payload, state, key)
        if annotation:
            order_id = state["documents"]["customerorder"]["id"]
            path = "entity/customerorder/" + order_id
            order = self.t.request(MS, path)
            if href(order.get("state", {})) != href(annotation["state"]) or order.get("description") != annotation["description"]:
                self.t.request(MS, path, "PUT", annotation)
                order = self.t.request(MS, path)
            if href(order.get("state", {})) != href(annotation["state"]) or order.get("description") != annotation["description"]:
                raise Stop("Customer order status/comment readback mismatch")
            state["order_annotation"] = {"state_name": self.c["order_annotation"]["state_name"], "description": annotation["description"]}
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
        if mode == "run":
            self._execution_permit = None
            decision = self.execution_permission()
            if decision:
                return decision
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
            permit = getattr(self, "_execution_permit", {})
            if permit.get("kind") == "manual" and supply_id not in permit["supply_ids"]:
                continue
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

