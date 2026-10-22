"""Read-only fixed-cost lookup for explicitly requested IP weekly report."""
import json
import fbs_document_chain as m
articles=["15-furpanama-cream","674-noelbag-pink","590-pamelabag-brown","553-ariadnabag-coffee"]
t=m.Transport();db=m.Cache(t);w=m.Worker(t,db,{})
out={"at":m.now(),"status":"reading","products":{}}
for article in articles:
 for p in w.ms_rows("entity/product",{"filter":"archived=false;article="+article}):
  a=(p.get("article") or "").strip().casefold()
  if a==article:
   out["products"].setdefault(a,[]).append({k:p.get(k) for k in ("id","article","name","buyPrice","salePrices","attributes","archived","uom")})
for article,products in out["products"].items():
 for p in products:
  try:
   p["stock_cost_rows"]=w.ms_rows("report/stock/all",{"filter":"product="+m.MS+"entity/product/"+p["id"],"stockMode":"all","quantityMode":"all"})
  except m.Stop as exc:p["stock_cost_error"]=str(exc)
out["status"]="verified" if all(len(out["products"].get(a,[]))==1 for a in articles) else "needs_review"
db.put("weekly_report_review:ip:20261012_18:costs:v1",out)
print(json.dumps({"status":out["status"],"articles":len(out["products"])}))
