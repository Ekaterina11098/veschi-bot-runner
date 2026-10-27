"""Reconcile incomplete Ozon chains in an explicitly authorized day; retain private API errors."""
import os,json,gzip,datetime as dt,urllib.request,urllib.error
import fbs_document_chain as m
from fbs_ozon_chain import acts,snapshot,OzonWorker,virtual_supply,CONFIG,PREFIX
original=urllib.request.urlopen
last_error={}
def capture(req,*a,**kw):
 try:return original(req,*a,**kw)
 except urllib.error.HTTPError as e:
  raw=e.read()
  if e.headers.get("Content-Encoding")=="gzip":raw=gzip.decompress(raw)
  try:last_error.update(json.loads(raw))
  except Exception:pass
  raise
urllib.request.urlopen=capture
t=m.Transport();db=m.Cache(t);root=os.environ["DAY_REVIEW_ROOT"];req=db.get(root+"request:v1")
assert req.get("authorized_repair") is True
config=db.get(CONFIG);assert config.get("writes_enabled") and config.get("status")=="active"
out={"at":m.now(),"status":"running","repairs":[],"errors":[]}
for act in acts():
 if act.get("departure_date")!=req["date"]:continue
 sid="OZON-ACT-"+str(act["id"]);key=PREFIX+sid;state=db.get(key)
 if state and state.get("status")=="complete":continue
 try:
  scope=snapshot(act)
  if not scope["ready"]:continue
  worker=OzonWorker(t,db,config,act,scope)
  state=state or {"act":act,"supply":virtual_supply(act,scope),"status":"discovered"}
  if state.get("picking_scope"):
   assert state["picking_scope"]["counts"]==scope["counts"] and state["picking_scope"]["included"]==scope["included"]
  state["picking_scope"]=scope
  old=db.get(root+"ozon_before:"+sid)
  if not old:db.put(root+"ozon_before:"+sid,state)
  db.put(root+"ozon_repair_progress:v1",{"at":m.now(),"supply_id":sid,"phase":"reconciling_inflight"})
  inflight=state.get("inflight")
  if inflight:
   ext=config["document_prefix"]+":"+sid+":"+inflight
   existing=worker.ms_rows("entity/"+inflight,{"filter":"externalCode="+ext});assert len(existing)<=1
   if not existing:
    if inflight=="salesreturn":
     parent=m.href(state["documents"]["demand"])
     parent_doc=t.request(m.MS,"entity/demand/"+state["documents"]["demand"]["id"])
     return_refs=parent_doc.get("returns",[])
     if not isinstance(return_refs,list):raise m.Stop("Unexpected parent return-link representation")
     linked=[t.request(m.MS,"entity/salesreturn/"+m.href(ref).rsplit("/",1)[-1]) for ref in return_refs if ref.get("meta",{}).get("type")=="salesreturn"]
     since=(dt.date.fromisoformat(req["date"])-dt.timedelta(days=1)).strftime("%Y-%m-%d")+" 00:00:00"
     # Direct demand.returns is the authoritative associated-return graph.
     db.put(root+"ozon_return_link_check:v1",{"at":m.now(),"demand_id":parent_doc["id"],"return_count":len(linked)})
     if linked:raise m.Stop("Existing linked manual return requires reconciliation")
    elif inflight=="demand":
     parent=m.href(state["documents"]["customerorder"])
     linked=[d for d in worker.ms_rows("entity/demand",{"filter":"agent="+m.href(config["templates"]["demand"]["agent"])}) if m.href(d.get("customerOrder",{}))==parent]
     if linked:raise m.Stop("Existing linked manual demand requires reconciliation")
    else:
     for name in [worker.order_name,worker.order_name+" "+str(act["id"])]:
      if any(d.get("description")==worker.comment for d in worker.ms_rows("entity/customerorder",{"filter":"name="+name})):raise m.Stop("Existing manual order requires reconciliation")
    state.pop("inflight",None);state["uncertain_reconciled_at"]=m.now();db.put(key,state)
  db.put(root+"ozon_repair_progress:v1",{"at":m.now(),"supply_id":sid,"phase":"resuming_verified_absent_document"})
  worker.process(state)
  out["repairs"].append({"supply_id":sid,"status":"verified","quantity":sum(scope["counts"].values()),"documents":state["documents"]})
 except Exception as e:
  out["errors"].append({"supply_id":sid,"error":str(e) if isinstance(e,m.Stop) else type(e).__name__,"api_error":dict(last_error)})
 db.put(root+"ozon_repair:v1",out)
out["status"]="complete" if not out["errors"] else "requires_attention";out["completed_at"]=m.now();db.put(root+"ozon_repair:v1",out)
print(json.dumps({"status":out["status"],"repaired":len(out["repairs"]),"errors":len(out["errors"])}))
if out["errors"]:raise SystemExit(1)
