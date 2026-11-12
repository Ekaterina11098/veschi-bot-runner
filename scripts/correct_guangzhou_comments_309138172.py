"""Update description only on the three already posted exact WB Guangzhou pilot documents."""
import copy, json
import fbs_document_chain as m

SID = "WB-GI-309138172"
NEW = "12 11 26 Китай Гуанджоу"
KEY = "fbs_document_chain:china:supply:v1:" + SID
t = m.Transport()
db = m.Cache(t)
state = db.get(KEY)
config = db.get(m.CONFIG)
if not state or state.get("status") != "complete" or state.get("supply",{}).get("id") != SID:
    raise m.Stop("Expected completed supply missing")
route = state.get("warehouse_routing") or {}
if route.get("wb_warehouse_id") != 2308581 or route.get("source_store_id") != "2233c6a7-d906-11f1-0a80-197e004df0d2" or route.get("return_store_id") != "c599b096-a784-11f1-0a80-15f1000f8193":
    raise m.Stop("Guangzhou warehouse routing mismatch")
if set(state.get("documents", {})) != set(m.TYPES) or len(state.get("order_ids", [])) != 2 or sum(p["quantity"] for p in state.get("positions", [])) != 2:
    raise m.Stop("Document chain scope mismatch")
old = state.get("order_annotation",{}).get("description")
if old not in ("12 11 26  Гонконг Гуанджоу", NEW):
    raise m.Stop("Unexpected previously approved description")
w = m.Worker(t, db, config)
docs={}
for typ in m.TYPES:
    info=state["documents"][typ]
    d=t.request(m.MS, "entity/"+typ+"/"+info["id"])
    expected_ext=config.get("document_prefix","fbs-china")+":"+SID+":"+typ
    if d.get("externalCode") != expected_ext or d.get("name") != info["name"]:
        raise m.Stop("MoySklad document identity mismatch")
    payload=copy.deepcopy(config["templates"][typ])
    payload["positions"]=state["positions"]
    payload["description"]=d.get("description")
    ident=route["return_store_id"] if typ=="salesreturn" else route["source_store_id"]
    payload["store"]["meta"]["href"]=m.MS+"entity/store/"+ident
    if typ=="demand":payload["customerOrder"]=state["documents"]["customerorder"]
    if typ=="salesreturn":payload["demand"]=state["documents"]["demand"]
    w.verify(typ,d,payload)
    if d.get("description") not in (old,NEW):
        raise m.Stop("Manual description change requires owner review")
    docs[typ]={"id":info["id"],"name":info["name"]}
for typ in m.TYPES:
    path="entity/"+typ+"/"+docs[typ]["id"]
    current=t.request(m.MS,path)
    if current.get("description")!=NEW:
        t.request(m.MS,path,"PUT",{"description":NEW})
    updated=t.request(m.MS,path)
    if updated.get("description")!=NEW:raise m.Stop("Document description readback mismatch")
# Save the authoritative expected description used by the continuous comment audit.
state["order_annotation"]["description"]=NEW
db.put(KEY,state)
print(json.dumps({"status":"complete","supply_id":SID,"description":NEW,"documents":{k:v["name"] for k,v in docs.items()}},ensure_ascii=False))
