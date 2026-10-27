"""Finalize an explicitly approved weekly chain after stock cost reconciliation."""
import os
from decimal import Decimal, ROUND_FLOOR
from collections import Counter
import fbs_document_chain as m

t=m.Transport(); db=m.Cache(t); w=m.Worker(t,db,{})
root=os.environ["WEEKLY_REVIEW_ROOT"]
approval=db.get(root+"finalization_request:v1")
assert approval and approval.get("authorized") is True
prior=db.get(root+"documents:v1"); plan=db.get(root+"plan:v1")
assert prior["status"]=="complete"
refs=prior["documents"]
assert len(refs)==5
ref=next(x for x in refs if x["type"]=="demand")
path="entity/demand/"+ref["id"]
doc=t.request(m.MS,path)
ps=w.ms_rows(path+"/positions",{"expand":"assortment","fields":"stock"})
actual=Counter()
for p in ps:
 actual[p["assortment"]["article"].strip().casefold()]+=p["quantity"]
assert dict(actual)==plan["sales"]
amount=0
for p in ps:
 q=Decimal(str(p["quantity"]))
 cost=Decimal(str(p.get("stock",{}).get("cost") or 0))
 assert cost>0, "Unresolved stock cost"
 amount+=int((cost/q).to_integral_value(rounding=ROUND_FLOOR))*q
assert amount==approval["expected_valuation_kopecks"]
assert plan["CK_sum"]==approval["expected_ck_rub"]
# Zero prices preserve existing position identities, quantities, tax and discount.
positions=[{"id":p["id"],"quantity":p["quantity"],"price":0,
 "discount":p.get("discount",0),"vat":p.get("vat",0),
 "vatEnabled":p.get("vatEnabled",False),"assortment":m.meta(p["assortment"])} for p in ps]
t.request(m.MS,path,method="PUT",body={"description":approval["comment"],"positions":positions,"applicable":True})
out={"at":m.now(),"status":"verifying","documents":[],"valuation_kopecks":int(amount),"CK_sum":plan["CK_sum"],"comment":approval["comment"]}
for ref in refs:
 pth="entity/"+ref["type"]+"/"+ref["id"]
 d=t.request(m.MS,pth,params={"expand":"state"})
 pp=w.ms_rows(pth+"/positions",{"expand":"assortment"})
 assert d.get("applicable") is True and d["sum"]==0
 assert all(p["price"]==0 for p in pp)
 if ref["type"]=="demand":assert d["description"]==approval["comment"]
 if ref["type"]=="customerorder":assert d.get("state",{}).get("name")==approval["order_state"]
 out["documents"].append({"type":ref["type"],"id":ref["id"],"name":d["name"],"posted":True,"sum":d["sum"],"description":d.get("description"),"quantity":sum(p["quantity"] for p in pp),"state":d.get("state",{}).get("name")})
out["status"]="complete"
db.put(root+"finalized:20261027:v1",out)
prior["demand_comment"]=approval["comment"];prior["valuation_kopecks"]=int(amount);prior["finalized_at"]=m.now()
db.put(root+"documents:v1",prior)
print("Approved weekly chain finalized; all five documents posted with zero prices.")
