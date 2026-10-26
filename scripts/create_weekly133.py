"""Create only the explicitly requested weekly document chain from a private approved plan."""
import json,collections,uuid,math,time,datetime
from decimal import Decimal,ROUND_FLOOR
import fbs_document_chain as m
ROOT="weekly_report_review:133:"
class T(m.Transport):
 def request(self,base,path,method="GET",body=None,params=None):
  for attempt in range(3):
   try:return super().request(base,path,method,body,params)
   except m.Stop:
    if method!="GET" or attempt==2:raise
    time.sleep(2*(attempt+1))
t=T();db=m.Cache(t);w=m.Worker(t,db,{})
plan=db.get(ROOT+"plan:v1");prep=db.get(ROOT+"prepare:v1")
assert plan and plan["authorized"] and plan["rules_version"]=="2026-10-26-reviewed"
assert prep["status"]=="prepared"
result=db.get(ROOT+"documents:v1") or {"status":"preflight","at":m.now(),"documents":[]}
def save():db.put(ROOT+"documents:v1",result)
def rows(path,params=None):return w.ms_rows(path,params)
def getdoc(kind,uid):return t.request(m.MS,"entity/"+kind+"/"+uid)
def ps(kind,uid,stock=False):return rows("entity/"+kind+"/"+uid+"/positions",{"expand":"assortment",**({"fields":"stock"} if stock else {})})
def counter(items):
 c=collections.Counter()
 for p in items:c[(p["assortment"].get("article") or "").strip().casefold()]+=p["quantity"]
 return dict(c)
products=prep["products"]
for a in set(plan["sales"])|set(plan["returns"]):assert len(products.get(a,[]))==1,("Product match",a)
common={k:m.meta(prep[k]) for k in ("organization","agent","store")}
common.update(applicable=True)
def check_common(d):
 return d.get("applicable") is True and all(m.href(d[k])==m.href(common[k]) for k in ("organization","agent","store"))
def pos(a,qty):
 return {"quantity":qty,"price":0,"discount":0,"vat":0,"assortment":m.meta(products[a][0])}
all_returns=rows("entity/salesreturn",{"filter":"organization="+m.href(common["organization"])+";store="+m.href(common["store"])+";moment>=2026-08-01 00:00:00"})
groups=collections.defaultdict(dict)
for a,qty in plan["returns"].items():groups[plan["basis"][a]][a]=qty
for uid,items in groups.items():
 d=getdoc("demand",uid);assert check_common(d),("Invalid basis",uid)
 basis=counter(ps("demand",uid));returned=collections.Counter()
 for r in all_returns:
  if r.get("externalCode","").startswith("weekly-ip-133-return-"):continue
  if m.href(r.get("demand",{}))==m.href(d):
   for a,q in counter(ps("salesreturn",r["id"])).items():returned[a]+=q
 for a,q in items.items():assert basis.get(a,0)-returned[a]>=q,("Insufficient return capacity",a,uid)
result["preflight_verified"]=True;save()
def ensure(kind,tag,body,wanted):
 ext="weekly-ip-133-"+tag
 matches=rows("entity/"+kind,{"filter":"externalCode="+ext})
 if kind=="customerorder":
  other=rows("entity/customerorder",{"filter":"name="+plan["name"]})
  if other and not matches:raise m.Stop("Existing order outside this run requires reconciliation")
 if len(matches)>1:raise m.Stop("Duplicate external code")
 if matches:d=matches[0]
 else:
  ident=str(uuid.uuid5(uuid.NAMESPACE_URL,"https://veschi/weekly/ip/883638535-883638538/"+kind+"/"+tag))
  try:d=getdoc(kind,ident)
  except m.Stop as exc:
   if not str(exc).startswith("HTTP_404"):raise
   d=t.request(m.MS,"entity/"+kind,"POST",{**body,"id":ident,"externalCode":ext})
 assert counter(ps(kind,d["id"]))==wanted,("Document items differ",kind,d["id"])
 assert check_common(d) and d["sum"]==0 and all(p["price"]==0 for p in ps(kind,d["id"]))
 entry={"type":kind,"id":d["id"],"name":d["name"]}
 if entry not in result["documents"]:result["documents"].append(entry);save()
 return d
order=ensure("customerorder","order",{**common,"name":plan["name"],"description":plan["comment"],"positions":[pos(a,q) for a,q in plan["sales"].items()]},plan["sales"])
demand=ensure("demand","demand",{**common,"customerOrder":m.meta(order),"description":plan["comment"],"positions":[pos(a,q) for a,q in plan["sales"].items()]},plan["sales"])
priced=ps("demand",demand["id"],True)
zero=[];valuation=0;valuations=[]
for p in priced:
 q=Decimal(str(p["quantity"]));cost=Decimal(str(p.get("stock",{}).get("cost") or 0))
 unit=int((cost/q).to_integral_value(rounding=ROUND_FLOOR))
 a=(p["assortment"].get("article") or "").strip().casefold()
 if unit<=0:zero.append(a)
 valuations.append({"article":a,"quantity":p["quantity"],"stock_cost":str(cost),"unit_price":unit});valuation+=Decimal(unit)*q
result["valuation_positions"]=valuations;result["zero_cost_articles"]=zero
result["valuation_kopecks"]=str(valuation);save()
if zero:
 result["status"]="needs_historical_cost";save();raise m.Stop("Zero valuation needs historical source")
def money(v):return format(Decimal(v)/100,",.2f").replace(","," ").replace(".",",")
ck=Decimal(str(plan["CK_sum"]))*100
comment="Опт: "+money(valuation)+" руб − рыжие возвраты "+money(ck)+" руб = "+money(valuation-ck)+" руб"
t.request(m.MS,"entity/demand/"+demand["id"],"PUT",{"description":comment,"applicable":True})
result["demand_comment"]=comment;save()
for uid,items in groups.items():
 basis=getdoc("demand",uid)
 ensure("salesreturn","return-"+uid,{**common,"demand":m.meta(basis),"description":"рыжие возвраты из "+plan["comment"],"positions":[pos(a,q) for a,q in items.items()]},items)
checks=[]
returned=collections.Counter()
for entry in result["documents"]:
 kind,uid=entry["type"],entry["id"];d=getdoc(kind,uid);items=ps(kind,uid)
 check={"type":kind,"id":uid,"name":d["name"],"posted":d.get("applicable") is True,"sum":d["sum"],"prices_zero":all(p["price"]==0 for p in items),"common":check_common(d),"quantity":sum(p["quantity"] for p in items),"positions":len(items),"comment":d.get("description",""),"items":counter(items)}
 if kind=="customerorder":
  check["comment_ok"]=d.get("description")==plan["comment"];check["items_ok"]=counter(items)==plan["sales"]
 elif kind=="demand":
  check["comment_ok"]=d.get("description")==comment;check["items_ok"]=counter(items)==plan["sales"];check["basis_ok"]=m.href(d.get("customerOrder",{}))==m.href(order)
 else:
  check["comment_ok"]=d.get("description")=="рыжие возвраты из "+plan["comment"]
  basisid=m.href(d["demand"]).split("/")[-1];check["items_ok"]=counter(items)==groups[basisid]
  returned.update(counter(items));check["basis_ok"]=check_common(getdoc("demand",basisid))
 assert all(check[k] for k in ("posted","prices_zero","common","comment_ok","items_ok")) and check["sum"]==0
 checks.append(check)
assert dict(returned)==plan["returns"]
result.update(status="complete",completed_at=m.now(),checks=checks,returns_match=True)
save();print(json.dumps({"status":"complete","documents":len(checks),"order_quantity":sum(plan["sales"].values()),"return_quantity":sum(returned.values())}))
