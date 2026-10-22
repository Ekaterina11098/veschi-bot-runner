"""User-authorized exact document-cost valuation, then restore zero prices."""
import json
import time
from decimal import Decimal, ROUND_DOWN
import fbs_document_chain as m
PATH="entity/demand/40ca02e6-cbbc-11f1-0a80-0c5400527d96"
KEY="weekly_report_review:demand:02729:document_cost:v2"
class Scoped(m.Transport):
 def request(self,base,path,method="GET",body=None,params=None):
  if base==m.MS and method!="GET":
   if method!="PUT" or path!=PATH or set(body)!={"positions"}:raise m.Stop("Out-of-scope write")
  return super().request(base,path,method,body,params)
t=Scoped();db=m.Cache(t);w=m.Worker(t,db,{})
prior=db.get(KEY)
if prior and prior.get("status")=="restored_verified":
 print("Already priced and restored");raise SystemExit
doc=t.request(m.MS,PATH)
ps=w.ms_rows(PATH+"/positions",{"fields":"stock"})
assert doc["name"]=="02729" and doc["sum"]==0 and all(p["price"]==0 for p in ps)
assert len(ps)==120 and sum(p["quantity"] for p in ps)==272
prices={}
for p in ps:
 cost=p.get("stock",{}).get("cost")
 assert cost is not None and cost>=0
 if cost==0:assert m.href(p["assortment"]).endswith("/93e21aa3-862f-11ef-0a80-096400115a88")
 prices[p["id"]]=int((Decimal(str(cost))/Decimal(str(p["quantity"]))).quantize(Decimal("1"),rounding=ROUND_DOWN))
total=sum(Decimal(prices[p["id"]])*Decimal(str(p["quantity"])) for p in ps)
assert total==Decimal("23193660"), "Document-cost valuation changed"
out={"at":m.now(),"before":doc,"original_positions":ps,"unit_prices_kopecks":prices,"calculated_sum_kopecks":float(total),"status":"prepared","basis":"document position stock.cost / quantity, fractional kopecks discarded, markup zero"}
db.put(KEY,out)
def payload(values):
 return {"positions":[{"meta":p["meta"],"quantity":p["quantity"],"price":values[p["id"]],"discount":p.get("discount",0),"vat":p.get("vat",0),"vatEnabled":p.get("vatEnabled",False),"assortment":p["assortment"]} for p in ps]}
def signature(rows):
 return sorted((p["id"],m.href(p["assortment"]),p["quantity"],p.get("discount",0),p.get("vat",0),p.get("vatEnabled",False)) for p in rows)
assert t.request(m.MS,PATH)["updated"]==doc["updated"]
out["status"]="restore_required";db.put(KEY,out)
try:
 priced=t.request(m.MS,PATH,"PUT",payload(prices))
 out["priced_sum_kopecks"]=priced["sum"]
 out["priced_positions"]=w.ms_rows(PATH+"/positions")
 assert priced["sum"]==23193660
 assert signature(out["priced_positions"])==signature(ps)
 assert all(p["price"]==prices[p["id"]] for p in out["priced_positions"])
 out["priced_verified"]=True
finally:
 for attempt in range(3):
  try:
   t.request(m.MS,PATH,"PUT",payload({p["id"]:p["price"] for p in ps}))
   after=t.request(m.MS,PATH);rows=w.ms_rows(PATH+"/positions")
   assert after["sum"]==0 and all(p["price"]==0 for p in rows)
   assert signature(rows)==signature(ps)
   for key in ("description","applicable","name","moment","organization","agent","store","customerOrder"):
    assert after.get(key)==doc.get(key), "Unexpected document field change"
   out["after"]=after;out["final_positions"]=rows;out["status"]="restored_verified";db.put(KEY,out)
   break
  except Exception:
   if attempt==2:raise
   time.sleep(2)
print(json.dumps({"status":out["status"],"priced_verified":out.get("priced_verified",False)}))
