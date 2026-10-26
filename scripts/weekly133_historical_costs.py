"""Read-only historical valuation lookup, only for zero-cost rows of the requested chain."""
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
root="weekly_report_review:133:"
result=db.get(root+"documents:v1");wanted=set(result["zero_cost_articles"]);prep=db.get(root+"prepare:v1")
out={"status":"reading","at":m.now(),"wanted":sorted(wanted),"history":{}}
demands=prep["demands"]
for d in demands:
 ps=w.ms_rows("entity/demand/"+d["id"]+"/positions",{"expand":"assortment","fields":"stock"})
 for p in ps:
  a=(p["assortment"].get("article") or "").strip().casefold()
  if a in wanted and (p.get("stock",{}).get("cost") or 0)>0:
   out["history"].setdefault(a,[]).append({"demand":d["id"],"name":d["name"],"moment":d["moment"],"order":d["customerOrder"]["name"],"quantity":p["quantity"],"stock":p["stock"]})
 db.put(root+"historical_costs:v1",out)
 if all(len(out["history"].get(a,[]))>=3 for a in wanted):break
out["status"]="found" if all(out["history"].get(a) for a in wanted) else "needs_older_history"
db.put(root+"historical_costs:v1",out);print(json.dumps({"status":out["status"],"found":len(out["history"])}))
