"""Reconcile explicitly supplied picking scopes against live documents, read-only."""
import json,collections,os
import fbs_document_chain as m
t=m.Transport();db=m.Cache(t);w=m.Worker(t,db,{})
root=os.environ["PICKING_REVIEW_ROOT"]; req=db.get(root+"request:v1")
assert req["mode"]=="audit"
recent={}
for typ in m.TYPES:
 recent[typ]=w.ms_rows("entity/"+typ,{"filter":"moment>=2026-10-26 00:00:00","order":"moment,desc"})
def count(ps):
 out=collections.Counter()
 for p in ps:out[(p["assortment"].get("article") or "").strip().casefold()]+=p["quantity"]
 return dict(out)
def audit(cabinet,sid,scope):
 c=db.get("fbs_document_chain:"+cabinet+":config:v1")
 state=db.get("fbs_document_chain:"+cabinet+":supply:v1:"+sid)
 assert state
 prefix=c.get("document_prefix","fbs-china")
 expected=scope["counts"]
 records=[]; selected={}
 for typ in m.TYPES:
  ext=prefix+":"+sid+":"+typ
  exact=w.ms_rows("entity/"+typ,{"filter":"externalCode="+ext})
  candidates={d["id"]:d for d in exact}
  old=state.get("documents",{}).get(typ)
  if old:candidates[old["id"]]=t.request(m.MS,"entity/"+typ+"/"+old["id"])
  for d in recent[typ]:
   if typ=="customerorder":
    match=d.get("name")==sid or (cabinet=="ozon" and any(n in (d.get("description") or "") for n in scope["order_ids"]))
   elif typ=="demand":match=m.href(d.get("customerOrder",{})) in selected.get("customerorder",[])
   else:match=m.href(d.get("demand",{})) in selected.get("demand",[])
   if match:candidates[d["id"]]=d
  selected[typ]=[m.href(d) for d in candidates.values() if not d.get("deleted")]
  for d in candidates.values():
   ps=w.ms_rows("entity/"+typ+"/"+d["id"]+"/positions",{"expand":"assortment"})
   actual=count(ps)
   records.append({"type":typ,"id":d["id"],"name":d["name"],"externalCode":d.get("externalCode"),"deleted":d.get("deleted"),"posted":d.get("applicable"),"sum":d["sum"],"description":d.get("description"),"counts":actual,"quantity":sum(actual.values()),"missing":dict(collections.Counter(expected)-collections.Counter(actual)),"extra":dict(collections.Counter(actual)-collections.Counter(expected)),"customerOrder":d.get("customerOrder"),"demand":d.get("demand"),"all_prices_zero":all(p["price"]==0 for p in ps)})
 return {"cabinet":cabinet,"supply_id":sid,"state_status":state.get("status"),"inflight":state.get("inflight"),"expected":expected,"expected_quantity":sum(expected.values()),"cached_quantity":sum(p["quantity"] for p in state.get("positions",[])),"documents":records,"scope":scope}
out={"at":m.now(),"status":"auditing","chains":[]}
for r in req["requests"]:out["chains"].append(audit(r["cabinet"],r["supply_id"],r))
for ident in req["ozon_acts"]:
 sid="OZON-ACT-"+str(ident);s=db.get("fbs_document_chain:ozon:supply:v1:"+sid)
 scope={"counts":s["picking_scope"]["counts"],"order_ids":s["order_ids"]}
 assert all(n in req["ozon_postings"] for n in scope["order_ids"])
 assert scope["counts"]==dict(collections.Counter(req["ozon_postings"][n] for n in scope["order_ids"]))
 out["chains"].append(audit("ozon",sid,scope))
out["status"]="audited";db.put(root+"audit:v1",out)
print(json.dumps({"status":"audited","chains":len(out["chains"])}))
