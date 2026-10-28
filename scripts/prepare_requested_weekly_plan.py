"""Read-only preparation of an explicitly requested weekly accounting chain."""
import os,json,time,collections
import fbs_document_chain as m
class ReadOnly(m.Transport):
 def request(self,base,path,method="GET",body=None,params=None):
  if base==m.MS and method!="GET":raise m.Stop("MS writes prohibited in preparation")
  return super().request(base,path,method,body,params)
t=ReadOnly();db=m.Cache(t);w=m.Worker(t,db,{})
root=os.environ["WEEKLY_REVIEW_ROOT"];inp=db.get(root+"input:v1");scope=db.get(root+"scope:v1")
assert inp and scope and scope["status"]=="read_verified"
prior=scope["orders"][0]["order"];store=scope["store"]
out={"status":"reading","at":m.now(),"organization":prior["organization"],"agent":prior["agent"],"store":store,"rate":prior.get("rate"),"products":{},"basis":[]}
wanted={a.strip().casefold() for a in inp["sales"]}|{a.strip().casefold() for a in inp["returns"]}
for p in w.ms_rows("entity/product",{"filter":"archived=false"}):
 a=(p.get("article") or "").strip().casefold()
 if a in wanted:out["products"].setdefault(a,[]).append({k:p.get(k) for k in ("id","article","name","meta","buyPrice")})
db.put(root+"prepare:v1",out)
stock=w.ms_rows("report/stock/all",{"filter":"store="+m.href(store),"stockMode":"all","quantityMode":"all"})
out["stock"]=[r for r in stock if any(m.href(p)==m.href(r) for ps in out["products"].values() for p in ps)]
out["stock_count"]=len(stock);db.put(root+"prepare:v1",out)
remaining=set(inp["returns"])
for old in scope["orders"]:
 for d in old["demands"]:
  if not remaining:break
  if not d.get("applicable"):continue
  pos=w.ms_rows("entity/demand/"+d["id"]+"/positions",{"expand":"assortment","fields":"stock"})
  matches=[p for p in pos if (p.get("assortment",{}).get("article") or "").strip().casefold() in remaining]
  if not matches:continue
  returns=[]
  for ref in d.get("returns",[]):
   r=t.request(m.MS,m.href(ref)[len(m.MS):])
   r["positions_full"]=w.ms_rows("entity/salesreturn/"+r["id"]+"/positions",{"expand":"assortment"})
   returns.append(r)
  item={"document":d,"positions":matches,"returns":returns};out["basis"].append(item)
  for p in matches:
   a=p["assortment"]["article"].strip().casefold();pid=p["assortment"]["id"]
   used=sum(q["quantity"] for r in returns if r.get("applicable") for q in r["positions_full"] if q["assortment"]["id"]==pid)
   if sum(q["quantity"] for q in matches if q["assortment"]["id"]==pid)-used>=inp["returns"].get(a,0):remaining.discard(a)
  db.put(root+"prepare:v1",out)
out["unresolved_basis"]=sorted(remaining);out["missing_products"]=sorted(wanted-set(out["products"]))
out["status"]="prepared";out["completed_at"]=m.now();db.put(root+"prepare:v1",out)
print(json.dumps({"status":out["status"],"products":len(out["products"]),"stock_rows":len(out["stock"]),"missing":len(out["missing_products"]),"basis":len(out["basis"]),"unresolved_basis":len(remaining)}))
