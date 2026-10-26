"""Read-only reconciliation of the approved weekly chain valuation."""
import json,time
from decimal import Decimal,ROUND_FLOOR,ROUND_HALF_UP
import fbs_document_chain as m
class T(m.Transport):
 def request(self,base,path,method="GET",body=None,params=None):
  if base==m.MS:assert method=="GET"
  for n in range(3):
   try:return super().request(base,path,method,body,params)
   except m.Stop:
    if method!="GET" or n==2:raise
    time.sleep(2)
t=T();db=m.Cache(t);w=m.Worker(t,db,{})
root="weekly_report_review:133:"
prior=db.get(root+"documents:v1");plan=db.get(root+"plan:v1")
assert prior["status"]=="complete"
out={"at":m.now(),"status":"reading","documents":[]}
old={x["article"]:x for x in prior["valuation_positions"]}
for ref in prior["documents"]:
 kind=ref["type"];uid=ref["id"]
 doc=t.request(m.MS,"entity/"+kind+"/"+uid,params={"expand":"state"})
 ps=w.ms_rows("entity/"+kind+"/"+uid+"/positions",{"expand":"assortment","fields":"stock"})
 record={"type":kind,"id":uid,"name":doc["name"],"moment":doc["moment"],"posted":doc.get("applicable"),"sum":doc["sum"],"description":doc.get("description"),"state":doc.get("state",{}).get("name"),"positions":[]}
 for p in ps:
  a=(p["assortment"].get("article") or "").strip().casefold()
  q=Decimal(str(p["quantity"]));cost=Decimal(str(p.get("stock",{}).get("cost") or 0))
  floor=int((cost/q).to_integral_value(rounding=ROUND_FLOOR))
  rnd=int((cost/q).to_integral_value(rounding=ROUND_HALF_UP))
  record["positions"].append({"article":a,"quantity":p["quantity"],"price":p["price"],"stock_cost":str(cost),"floor_unit_kopecks":floor,"rounded_unit_kopecks":rnd})
 if kind=="demand":
  pp=record["positions"]
  record["floor_total_kopecks"]=str(sum(Decimal(p["floor_unit_kopecks"])*Decimal(str(p["quantity"])) for p in pp))
  record["rounded_total_kopecks"]=str(sum(Decimal(p["rounded_unit_kopecks"])*Decimal(str(p["quantity"])) for p in pp))
  record["stock_total_kopecks"]=str(sum(Decimal(p["stock_cost"]) for p in pp))
  record["prior_comparison"]=[{"article":p["article"],"old":old.get(p["article"]),"current":p} for p in pp if str(old.get(p["article"],{}).get("stock_cost"))!=p["stock_cost"]]
 out["documents"].append(record)
out["status"]="read_verified";db.put(root+"valuation_audit:20261026:v1",out)
print(json.dumps({"status":out["status"],"documents":len(out["documents"])}))
