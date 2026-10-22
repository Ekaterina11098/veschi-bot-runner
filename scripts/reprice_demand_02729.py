"""One-off user-authorized pricing check for demand 02729, restoring original zero prices."""
import copy
import json
import time
from decimal import Decimal, ROUND_HALF_UP
import fbs_document_chain as m
PATH="entity/demand/40ca02e6-cbbc-11f1-0a80-0c5400527d96"
KEY="weekly_report_review:demand:02729:repricing:v1"
class Scoped(m.Transport):
 def request(self,base,path,method="GET",body=None,params=None):
  if base==m.MS and method!="GET":
   if method!="PUT" or path!=PATH or set(body)!={"positions"}:raise m.Stop("Out-of-scope write")
  return super().request(base,path,method,body,params)
t=Scoped();db=m.Cache(t);w=m.Worker(t,db,{})
prior=db.get(KEY)
if prior and prior.get("status")=="restored_verified":
 print("Already verified and restored");raise SystemExit
doc=t.request(m.MS,PATH)
ps=w.ms_rows(PATH+"/positions")
assert doc["name"]=="02729" and doc["sum"]==0 and all(p["price"]==0 for p in ps)
assert len(ps)==120 and sum(p["quantity"] for p in ps)==272
out={"at":m.now(),"status":"reading_costs","before":doc,"original_positions":ps,"costs":prior.get("costs",[]) if prior else [],"missing":[]}
done={p["id"] for p in out["costs"]}
db.put(KEY,out)
for p in ps:
 if p["id"] in done:continue
 if m.href(p["assortment"]).endswith("/93e21aa3-862f-11ef-0a80-096400115a88"):
  out["costs"].append({"id":p["id"],"quantity":p["quantity"],"price":0,"source":"User-authorized zero for mapped belt on 2026-10-22"})
  db.put(KEY,out);continue
 rows=w.ms_rows("report/stock/all",{"filter":"product="+m.href(p["assortment"]),"stockMode":"all","quantityMode":"all"})
 if len(rows)!=1 or rows[0].get("price",0)<=0:
  item={"position":p,"stock_rows":rows}
  item["product"]=t.request(m.MS,m.href(p["assortment"])[len(m.MS):])
  try:item["historical_stock"]=w.ms_rows("report/stock/all",{"filter":"product="+m.href(p["assortment"]),"stockMode":"all","quantityMode":"all","moment":doc["moment"]})
  except Exception as e:item["historical_error"]=str(e)
  out["missing"].append(item);db.put(KEY,out);continue
 out["costs"].append({"id":p["id"],"quantity":p["quantity"],"stock":rows[0],"price":float(Decimal(str(rows[0]["price"])).quantize(Decimal("1"),rounding=ROUND_HALF_UP))})
 db.put(KEY,out)
if out["missing"]:
 out["status"]="missing_costs";db.put(KEY,out);print("Missing costs recorded privately");raise SystemExit
total=sum(Decimal(str(c["price"]))*Decimal(str(c["quantity"])) for c in out["costs"])
out["calculated_sum_kopecks"]=float(total)
out["comparison_target_kopecks"]=23193660
out["difference_kopecks"]=float(total-Decimal("23193660"))
out["status"]="calculated"
db.put(KEY,out)
# Do not apply an unidentified valuation if cost pricing does not reproduce the target.
if total!=Decimal("22783906"):
 out["status"]="valuation_differs";db.put(KEY,out);print("Valuation differs; original document untouched");raise SystemExit
def payload(prices):
 return {"positions":[{"meta":p["meta"],"quantity":p["quantity"],"price":prices[p["id"]],"discount":p.get("discount",0),"vat":p.get("vat",0),"vatEnabled":p.get("vatEnabled",False),"assortment":p["assortment"]} for p in ps]}
def signature(rows):
 return sorted((p["id"],m.href(p["assortment"]),p["quantity"],p.get("discount",0),p.get("vat",0),p.get("vatEnabled",False)) for p in rows)
fresh=t.request(m.MS,PATH)
assert fresh["updated"]==doc["updated"], "Document changed during reading"
out["status"]="restore_required";db.put(KEY,out)
try:
 priced=t.request(m.MS,PATH,"PUT",payload({c["id"]:c["price"] for c in out["costs"]}))
 out["priced_sum_kopecks"]=priced["sum"]
 assert priced["sum"]==float(total)
 check=w.ms_rows(PATH+"/positions")
 assert signature(check)==signature(ps)
 out["priced_positions_verified"]=True
finally:
 for attempt in range(3):
  try:
   t.request(m.MS,PATH,"PUT",payload({p["id"]:p["price"] for p in ps}))
   after=t.request(m.MS,PATH);current=w.ms_rows(PATH+"/positions")
   assert after["sum"]==0 and all(p["price"]==0 for p in current)
   assert signature(current)==signature(ps)
   assert after.get("description")==doc.get("description") and after["applicable"]==doc["applicable"]
   out["after"]=after;out["status"]="restored_verified";db.put(KEY,out)
   break
  except Exception:
   if attempt==2:raise
   time.sleep(2)
print(json.dumps({"status":out["status"]}))
