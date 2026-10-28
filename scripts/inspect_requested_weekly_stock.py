"""Read stock and costs only; no accounting writes."""
import os,json
import fbs_document_chain as m
t=m.Transport();db=m.Cache(t);w=m.Worker(t,db,{})
root=os.environ["WEEKLY_REVIEW_ROOT"];p=db.get(root+"prepare:v1");inp=db.get(root+"input:v1")
assert p and p["status"]=="prepared"
out={"status":"reading","at":m.now(),"stock":[],"return_cost_stock":{}}
out["stock"]=w.ms_rows("report/stock/all",{"filter":"store="+m.href(p["store"]),"stockMode":"all","quantityMode":"all"})
db.put(root+"stock:v1",out)
for a in inp["returns"]:
 products=p["products"][a]
 assert len(products)==1
 out["return_cost_stock"][a]=w.ms_rows("report/stock/all",{"filter":"product="+m.href(products[0]),"stockMode":"all","quantityMode":"all"})
out["status"]="read_verified";out["at"]=m.now();db.put(root+"stock:v1",out)
print(json.dumps({"status":out["status"],"stock_rows":len(out["stock"]),"return_cost_articles":len(out["return_cost_stock"])}))
