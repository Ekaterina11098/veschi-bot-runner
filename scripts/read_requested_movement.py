"""Read requested stock movement only; never modify accounting documents."""
import json
import fbs_document_chain as m
class ReadOnly(m.Transport):
 def request(self,base,path,method="GET",body=None,params=None):
  if base==m.MS and method!="GET":raise m.Stop("Accounting writes prohibited")
  return super().request(base,path,method,body,params)
t=ReadOnly();db=m.Cache(t);w=m.Worker(t,db,{})
cfg=db.get("movement_reconciliation:request:v1");assert cfg and cfg["name"]
out={"status":"reading","documents":[],"at":m.now()}
for d in w.ms_rows("entity/move",{"filter":"name="+cfg["name"]}):
 doc=t.request(m.MS,"entity/move/"+d["id"],params={"expand":"organization,sourceStore,targetStore"})
 doc["positions_full"]=w.ms_rows("entity/move/"+d["id"]+"/positions",{"expand":"assortment"})
 out["documents"].append(doc)
out["status"]="read_verified";db.put("movement_reconciliation:move:"+cfg["name"]+":v1",out)
print(json.dumps({"status":"read_verified","matches":len(out["documents"])}))
