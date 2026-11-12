"""Exact owner-approved Guangzhou one-time run. Fail closed on ambiguous documents."""
import json
import fbs_document_chain as m

SID = "WB-GI-309138172"
t = m.Transport()
db = m.Cache(t)
c = db.get(m.CONFIG)
if not c or c.get("cabinet") != "token_3" or not c.get("writes_enabled") or c.get("status") != "active":
    raise m.Stop("China document worker is not active")
w = m.Worker(t, db, c)
# Require the existing owner approval gate before any operational writes.
decision = w.execution_permission(direct=True)
if decision:
    raise m.Stop(decision["reason"])
permit = w._execution_permit
if permit["kind"] != "manual" or permit["supply_ids"] != {SID}:
    raise m.Stop("Approval must cover exactly this one WB supply")
existing = db.get(m.PREFIX + SID)
if existing and existing.get("status") == "complete":
    print(json.dumps({"status": "already_complete", "documents": existing.get("documents", {})}))
    raise SystemExit(0)
if existing and (existing.get("inflight") or existing.get("documents") or existing.get("positions")):
    raise m.Stop("Partial chain already exists; manual reconciliation required")
supplies = [s for s in w.supplies() if s.get("id") == SID]
if len(supplies) != 1 or not supplies[0].get("done"):
    raise m.Stop("Exact WB supply not closed or not unique")
supply = supplies[0]
if m.stamp(supply["closedAt"]).date().isoformat() != "2026-11-12":
    raise m.Stop("Supply closed date differs")
state = {"supply": supply, "status": "discovered", "discovered_at": m.now()}
# Stock preflight, WB per-order warehouse check, and document idempotency are in Worker.process().
w.process(state)
if state.get("status") != "complete":
    raise m.Stop("Chain not fully completed")
documents = {}
for kind in m.TYPES:
    d = t.request(m.MS, "entity/" + kind + "/" + state["documents"][kind]["id"])
    expected = "2233c6a7-d906-11f1-0a80-197e004df0d2" if kind != "salesreturn" else "c599b096-a784-11f1-0a80-15f1000f8193"
    if m.href(d["store"]).rsplit("/", 1)[-1] != expected or d.get("applicable") is not True or d.get("sum") != 0:
        raise m.Stop("Warehouse/posting/sum verification failed for " + kind)
    docs_positions = w.ms_rows("entity/" + kind + "/" + d["id"] + "/positions")
    if sum(x["quantity"] for x in docs_positions) != 2 or any(x["price"] != 0 for x in docs_positions):
        raise m.Stop("Document positions mismatch")
    documents[kind] = d["name"]
print(json.dumps({"status": "complete", "supply": SID, "documents": documents}, ensure_ascii=False))
