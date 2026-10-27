"""Recover one explicitly requested Ozon act with private validation diagnostics."""
import os,json,gzip,urllib.request,urllib.error
import fbs_document_chain as m
from fbs_ozon_chain import OzonWorker,snapshot,CONFIG,PREFIX
original_open=urllib.request.urlopen
last_error={}
def capture_open(req,*args,**kwargs):
 try:return original_open(req,*args,**kwargs)
 except urllib.error.HTTPError as e:
  raw=e.read()
  if e.headers.get("Content-Encoding")=="gzip":raw=gzip.decompress(raw)
  try:last_error.update(json.loads(raw))
  except Exception:pass
  raise
urllib.request.urlopen=capture_open
t=m.Transport();db=m.Cache(t)
root=os.environ["PICKING_REVIEW_ROOT"];req=db.get(root+"request:v1");prior=db.get(root+"result:v1")
assert req.get("authorized_create") and req.get("mode")=="apply"
failed=[x for x in prior["chains"] if x["status"]=="failed" and x["cabinet"]=="ozon"]
assert len(failed)==1
sid=failed[0]["supply_id"];key=PREFIX+sid;state=db.get(key);c=db.get(CONFIG)
scope=snapshot(state["act"]);assert scope["ready"]
assert all(n in req["ozon_postings"] for n in scope["included"])
worker=OzonWorker(t,db,c,state["act"],scope)
ext=c["document_prefix"]+":"+sid+":customerorder"
found=worker.ms_rows("entity/customerorder",{"filter":"externalCode="+ext});assert len(found)<=1
if not found:
 existing=worker.ms_rows("entity/customerorder",{"filter":"name="+worker.order_name})
 assert not any(d.get("description")==worker.comment for d in existing)
 state.pop("inflight",None);db.put(key,state)
try:
 worker.process(state)
 result={"status":"verified","at":m.now(),"supply_id":sid,"documents":state["documents"],"quantity":sum(p["quantity"] for p in state["positions"])}
 db.put(root+"ozon_recovery:v1",result)
except Exception as e:
 db.put(root+"ozon_validation_error:v1",{"at":m.now(),"error":last_error,"exception":str(e) if isinstance(e,m.Stop) else type(e).__name__})
 raise
print("Requested Ozon recovery verified.")
