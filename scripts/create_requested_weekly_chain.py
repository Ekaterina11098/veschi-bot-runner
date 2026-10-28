"""Create the user-requested weekly chain only from a private verified plan."""
import os,json,collections,uuid,datetime,time
from decimal import Decimal,ROUND_FLOOR,ROUND_HALF_UP
import fbs_document_chain as m
t=m.Transport();db=m.Cache(t);w=m.Worker(t,db,{})
root=os.environ["WEEKLY_REVIEW_ROOT"];plan=db.get(root+"plan:v1");prep=db.get(root+"prepare:v1");request=db.get(root+"request:v1")
assert plan and plan["authorized"] is True and request["writes_authorized"] is True
assert plan["excel_verified"] is True and prep["status"]=="prepared"
assert datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).date().isoformat()==plan["prepared_on"]
result=db.get(root+"documents:v1") or {"status":"preflight","documents":[],"at":m.now()}
def save():db.put(root+"documents:v1",result)
def rows(path,params=None):return w.ms_rows(path,params)
def getdoc(kind,ident):return t.request(m.MS,"entity/"+kind+"/"+ident)
def positions(kind,ident,stock=False):return rows("entity/"+kind+"/"+ident+"/positions",{"expand":"assortment",**({"fields":"stock"} if stock else {})})
def normalized(ref):return m.href(ref).split("?")[0]
def counter(pos):
 c=collections.Counter()
 for p in pos:c[(p["assortment"].get("article") or "").strip().casefold()]+=p["quantity"]
 return dict(c)
products=prep["products"]
for a in set(plan["sales"])|set(plan["returns"]):assert len(products.get(a,[]))==1,("Ambiguous product",a)
common={k:m.meta(prep[k]) for k in ("organization","agent","store")};common["applicable"]=True
common["rate"]={"currency":m.meta(prep["rate"]["currency"])}
def same_scope(doc):return doc.get("applicable") is True and all(normalized(doc[k])==normalized(common[k]) for k in ("organization","agent","store"))
stock=rows("report/stock/all",{"filter":"store="+normalized(common["store"]),"stockMode":"all","quantityMode":"all"})
byid={normalized(r):r for r in stock};exceptions=[]
for a,q in plan["sales"].items():
 r=byid.get(normalized(products[a][0]),{})
 if r.get("stock",0)<q or r.get("price",0)<=0:exceptions.append({"article":a,"wanted":q,"stock":r.get("stock",0),"cost":r.get("price",0)})
result["stock_exceptions"]=exceptions;save()
if exceptions:raise m.Stop("Actual stock or cost requires clarification; no inventory fabricated")
state=[s for s in t.request(m.MS,"entity/customerorder/metadata").get("states",[]) if s.get("name")=="Доставлен"]
assert len(state)==1,"Delivered order state missing or ambiguous"
groups=collections.defaultdict(dict)
for a,q in plan["returns"].items():groups[plan["basis"][a]][a]=q
prefix=plan["external_prefix"]
for ident,items in groups.items():
 d=getdoc("demand",ident);assert same_scope(d)
 capacity=collections.Counter(counter(positions("demand",ident)));used=collections.Counter()
 for ref in d.get("returns",[]):
  r=t.request(m.MS,normalized(ref)[len(m.MS):])
  if not r.get("applicable") or r.get("externalCode","").startswith(prefix+"return-"):continue
  used.update(counter(positions("salesreturn",r["id"])))
 for a,q in items.items():assert capacity[a]-used[a]>=q,("Insufficient return capacity",a)
result["status"]="creating";save()
def make_position(a,q):return {"quantity":q,"price":0,"discount":0,"vat":0,"assortment":m.meta(products[a][0])}
def ensure(kind,tag,body,wanted):
 ext=prefix+tag;matches=rows("entity/"+kind,{"filter":"externalCode="+ext})
 if len(matches)>1:raise m.Stop("Duplicate external code")
 if kind=="customerorder":
  named=rows("entity/customerorder",{"filter":"name="+plan["name"]})
  if any(x["id"] not in {v["id"] for v in matches} for x in named):raise m.Stop("Existing order requires reconciliation")
 if matches:doc=matches[0]
 else:
  ident=str(uuid.uuid5(uuid.NAMESPACE_URL,root+kind+"/"+tag))
  try:doc=getdoc(kind,ident)
  except m.Stop as exc:
   if not str(exc).startswith("HTTP_404"):raise
   doc=t.request(m.MS,"entity/"+kind,"POST",{**body,"id":ident,"externalCode":ext})
 ps=positions(kind,doc["id"])
 assert same_scope(doc) and doc["sum"]==0 and all(p["price"]==0 for p in ps)
 assert counter(ps)==wanted,("Unexpected document items",kind,doc["id"])
 record={"type":kind,"id":doc["id"],"name":doc["name"]}
 if record not in result["documents"]:result["documents"].append(record);save()
 return doc
order=ensure("customerorder","order",{**common,"name":plan["name"],"description":plan["comment"],"state":m.meta(state[0]),"positions":[make_position(a,q) for a,q in plan["sales"].items()]},plan["sales"])
demand=ensure("demand","demand",{**common,"description":plan["comment"],"customerOrder":m.meta(order),"positions":[make_position(a,q) for a,q in plan["sales"].items()]},plan["sales"])
valuation=Decimal(0);proof=[]
for attempt in range(3):
 valuation=Decimal(0);proof=[];bad=[]
 for p in positions("demand",demand["id"],True):
  q=Decimal(str(p["quantity"]));cost=Decimal(str(p.get("stock",{}).get("cost") or 0));unit=(cost/q).to_integral_value(rounding=ROUND_FLOOR)
  a=p["assortment"]["article"].strip().casefold()
  if unit<=0:bad.append(a)
  proof.append({"article":a,"quantity":str(q),"actual_stock_cost_kopecks":str(cost),"unit_price_kopecks":str(unit)});valuation+=unit*q
 if not bad:break
 time.sleep(2)
result.update(valuation_positions=proof,valuation_kopecks=str(valuation),zero_or_negative_cost_articles=bad);save()
if bad:raise m.Stop("Document cost requires clarification; all prices remain zero")
fx=plan["fx"];opt_rub=valuation/100
opt_foreign=(opt_rub*Decimal(str(fx["nominal"]))/Decimal(str(fx["rub"]))).quantize(Decimal(".01"),rounding=ROUND_HALF_UP)
ck=Decimal(str(plan["CK_sum"]));net=opt_foreign-ck
def money(x):return format(Decimal(x),",.2f").replace(","," ").replace(".",",")
comment="Опт: "+money(opt_rub)+" руб. = "+money(opt_foreign)+" сом − рыжие возвраты "+money(ck)+" сом = "+money(net)+" сом. Курс ЦБ на "+plan["fx_date_label"]+": 100 сом = "+str(fx["rub"]).replace(".",",")+" руб."
t.request(m.MS,"entity/demand/"+demand["id"],"PUT",{"description":comment,"applicable":True})
result["demand_comment"]=comment;result["net_KGS"]=str(net);save()
for ident,items in groups.items():
 ensure("salesreturn","return-"+ident,{**common,"description":"рыжие возвраты из "+plan["comment"],"demand":m.meta(getdoc("demand",ident)),"positions":[make_position(a,q) for a,q in items.items()]},items)
checks=[];returns=collections.Counter()
for e in result["documents"]:
 kind=e["type"];doc=getdoc(kind,e["id"]);ps=positions(kind,doc["id"]);items=counter(ps)
 check={**e,"posted":doc.get("applicable") is True,"prices_zero":all(p["price"]==0 for p in ps),"sum":doc["sum"],"scope_ok":same_scope(doc),"items":items,"quantity":sum(items.values()),"comment":doc.get("description","")}
 if kind=="customerorder":
  check["items_ok"]=items==plan["sales"];check["comment_ok"]=doc.get("description")==plan["comment"];check["state_ok"]=normalized(doc.get("state",{}))==normalized(state[0])
  assert check["state_ok"]
 elif kind=="demand":
  check["items_ok"]=items==plan["sales"];check["comment_ok"]=doc.get("description")==comment;check["basis_ok"]=normalized(doc.get("customerOrder",{}))==normalized(order);assert check["basis_ok"]
 else:
  ident=normalized(doc.get("demand",{})).split("/")[-1];check["items_ok"]=items==groups[ident];check["comment_ok"]=doc.get("description")=="рыжие возвраты из "+plan["comment"];returns.update(items)
 assert all(check[k] for k in ("posted","prices_zero","scope_ok","items_ok","comment_ok")) and check["sum"]==0
 check["external_code_unique"]=len(rows("entity/"+kind,{"filter":"externalCode="+doc["externalCode"]}))==1;assert check["external_code_unique"]
 checks.append(check)
assert dict(returns)==plan["returns"] and len(checks)==2+len(groups)
fresh_order=getdoc("customerorder",order["id"]);assert [normalized(x) for x in fresh_order.get("demands",[])]==[normalized(demand)]
result.update(status="complete",completed_at=m.now(),checks=checks,returns_match=True,order_demand_link_verified=True,all_prices_zero=True,all_posted=True)
save();print(json.dumps({"status":"complete","documents":len(checks),"sales_units":sum(plan["sales"].values()),"returns_units":sum(returns.values())}))
