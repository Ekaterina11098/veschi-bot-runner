"""Read-only lookup of one supply chain requested through private cache."""
import json,time
import fbs_document_chain as m
class ReadOnly(m.Transport):
 def request(self,base,path,method="GET",body=None,params=None):
  if base==m.MS:assert method=="GET"
  return super().request(base,path,method,body,params)
t=ReadOnly();db=m.Cache(t);c=db.get(m.CONFIG);req=db.get("fbs_document_chain:china:document_audit_request:v1")
sid=req["supply_id"];w=m.Worker(t,db,c)
out={"at":m.now(),"supply_id":sid,"status":"reading","documents":[],"errors":[]}
try:
 orders=w.ms_rows("entity/customerorder",{"filter":"name="+sid})
 docs={("customerorder",x["id"]):x for x in orders}
 for kind in m.TYPES:
  ext=c.get("document_prefix","fbs-china")+":"+sid+":"+kind
  for d in w.ms_rows("entity/"+kind,{"filter":"externalCode="+ext}):docs[(kind,d["id"])]=d
 for (kind,uid),d in list(docs.items()):
  if kind=="customerorder":
   for dd in w.ms_rows("entity/demand",{"filter":"customerOrder="+m.href(d)}):docs[("demand",dd["id"])]=dd
 for (kind,uid),d in list(docs.items()):
  if kind=="demand":
   for dd in w.ms_rows("entity/salesreturn",{"filter":"demand="+m.href(d)}):docs[("salesreturn",dd["id"])]=dd
 for (kind,uid),d in docs.items():
  ps=w.ms_rows("entity/"+kind+"/"+uid+"/positions")
  out["documents"].append({"type":kind,"id":uid,"name":d["name"],"created":d.get("created"),"updated":d.get("updated"),"moment":d.get("moment"),"posted":d.get("applicable"),"sum":d.get("sum"),"quantity":sum(p["quantity"] for p in ps),"positions":len(ps),"prices_zero":all(p["price"]==0 for p in ps),"comment":d.get("description")})
 out["status"]="read_verified"
except m.Stop as e:
 out["status"]="api_unavailable";out["errors"].append(str(e))
out["completed_at"]=m.now();db.put("fbs_document_chain:china:document_audit:v1:"+sid,out)
print(json.dumps({"status":out["status"],"documents":len(out["documents"]),"errors":out["errors"]}))
