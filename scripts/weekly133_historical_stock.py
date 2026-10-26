"""Read historical stock snapshots for unresolved weekly valuation rows."""
import json,time
import fbs_document_chain as m
class T(m.Transport):
 def request(self,base,path,method="GET",body=None,params=None):
  if base==m.MS and method!="GET":raise m.Stop("MS writes prohibited")
  for attempt in range(3):
   try:return super().request(base,path,method,body,params)
   except m.Stop:
    if method!="GET" or attempt==2:raise
    time.sleep(2*(attempt+1))
t=T();db=m.Cache(t);w=m.Worker(t,db,{})
root="weekly_report_review:133:";prep=db.get(root+"prepare:v1");doc=db.get(root+"documents:v1")
out=db.get(root+"historical_costs:v1");out["stock_snapshots"]={};out["status"]="reading_stock"
for a in doc["zero_cost_articles"]:
 if out["history"].get(a):continue
 pid=prep["products"][a][0]["id"]
 for date in ("2026-10-18","2026-09-30","2026-08-31","2026-07-31","2026-06-30","2026-03-31","2025-12-31","2025-11-30","2025-10-31","2024-12-31"):
  rows=w.ms_rows("report/stock/all",{"filter":"product="+m.MS+"entity/product/"+pid+";moment="+date+" 23:59:59;stockMode=all;quantityMode=all"})
  out["stock_snapshots"].setdefault(a,[]).append({"moment":date+" 23:59:59","rows":[{k:r.get(k) for k in ("article","price","stock","quantity","reserve")} for r in rows]})
  db.put(root+"historical_costs:v1",out)
  if sum(any((r.get("price") or 0)>0 and (r.get("stock") or 0)>0 for r in x["rows"]) for x in out["stock_snapshots"][a])>=3:break
out["status"]="historical_stock_read";db.put(root+"historical_costs:v1",out)
print(json.dumps({"status":out["status"],"articles":len(out["stock_snapshots"])}))
