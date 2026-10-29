"""Create the privately requested zero-price China return move after exact stock checks."""
import collections,datetime as dt,json,re,math
import fbs_document_chain as m
ROOT="returns_transfer:china:20261028:"
t=m.Transport();db=m.Cache(t);w=m.Worker(t,db,{})
req=db.get(ROOT+"request:v1")
def norm(x):return x.strip().casefold().replace("c","с")
def code(item):
 match=re.fullmatch(r"(зонт|панама|манишка|ремень|шарф)\s*—\s*(\d+)",item)
 if match:return str(int(match[2]))+{"зонт":"з","панама":"м","манишка":"м","ремень":"р","шарф":"м"}[match[1]]
 assert re.fullmatch(r"\d+",item)
 return ("0" if item=="00" else item)+"с"
def totals(ps):
 values=collections.Counter()
 for p in ps:values[m.href(p["assortment"])]+=p["quantity"]
 return values
def save(x):db.put(ROOT+"result:v1",x)
result={"status":"mapping","write_attempted":False,"at":m.now()}
try:
 assert req["writes_enabled"] is True and len(req["rows"])==req["total"]==77
 stores=w.ms_rows("entity/store")
 source=[s for s in stores if s["id"]==req["source_store_id"] and s["name"]==req["source_store_name"] and not s.get("archived")]
 target=[s for s in stores if s["id"]==req["target_store_id"] and s["name"]==req["target_store_name"] and not s.get("archived")]
 assert len(source)==len(target)==1,"Warehouse identity missing or ambiguous"
 source=source[0];target=target[0]
 orgs=w.ms_rows("entity/organization");assert len(orgs)==1
 products=w.ms_rows("entity/product")
 by=collections.defaultdict(list)
 for p in products:
  if not p.get("archived"):by[norm(p.get("code",""))].append(p)
 mapping=[];issues=[]
 for key,quantity in collections.Counter(code(x) for x in req["rows"]).items():
  found=by[norm(key)]
  if not found and key.endswith("с"):
   number=int(key[:-1])
   found=[p for p in products if not p.get("archived") and re.fullmatch(r"\d+с",norm(p.get("code",""))) and int(norm(p["code"])[:-1])==number]
  if len(found)!=1:
   issues.append({"issue":"product_mapping","code":key,"quantity":quantity,"matches":[{"id":p["id"],"article":p.get("article"),"code":p.get("code"),"name":p["name"]} for p in found]});continue
  p=found[0];assert not p.get("variantsCount",0),"Variant mapping required"
  mapping.append({"id":p["id"],"source_code":key,"code":p["code"],"article":p.get("article"),"name":p["name"],"quantity":quantity,"assortment":m.meta(p)})
 result.update(mapping=mapping,issues=issues,total=77,source=source["name"],target=target["name"])
 if issues:
  result["status"]="needs_mapping";save(result);raise m.Stop("Product mapping needs review")
 expected=collections.Counter()
 for p in mapping:expected[m.href(p["assortment"])]+=p["quantity"]
 assert sum(expected.values())==77
 docs=w.ms_rows("entity/move",{"filter":"externalCode="+req["externalCode"]})
 assert len(docs)<=1,"Duplicate external identity"
 state=db.get(ROOT+"creation:v1")
 if docs:doc=docs[0]
 else:
  assert not state or state.get("status") not in ("inflight","created"),"Prior creation outcome uncertain; reconcile instead of retrying"
  candidates=w.ms_rows("entity/move")
  matching=[]
  for d in candidates:
   if d.get("deleted") or (d.get("description") or "").strip().casefold()!=req["description"].strip().casefold():continue
   if m.href(d.get("sourceStore",{}))!=m.href(source) or m.href(d.get("targetStore",{}))!=m.href(target):continue
   if totals(w.ms_rows("entity/move/"+d["id"]+"/positions"))==expected:matching.append(d)
  assert len(matching)<=1,"Multiple matching documents"
  if matching:doc=matching[0]
  else:
   stock=t.request(m.MS,"report/stock/bystore/current",params={"stockType":"freeStock","include":"zeroLines"})
   assert isinstance(stock,list),"Current warehouse stock report incomplete"
   index={}
   for row in stock:
    pair=(row["storeId"],row["assortmentId"])
    assert pair not in index
    index[pair]=row["freeStock"]
   shortages=[]
   for p in mapping:
    pair=(source["id"],p["id"])
    if pair not in index:
     shortages.append({"issue":"stock_unknown","article":p["article"],"code":p["code"],"required":p["quantity"]});continue
    available=index[pair];assert type(available) in (int,float) and math.isfinite(available)
    p["available_before"]=available
    if available<p["quantity"]:shortages.append({"issue":"shortage","article":p["article"],"code":p["code"],"name":p["name"],"required":p["quantity"],"available":available,"missing":p["quantity"]-available})
   result.update(status="prepared" if not shortages else "insufficient_stock",mapping=mapping,issues=shortages,stock_checked_at=m.now());save(result)
   if shortages:raise m.Stop("Available source stock insufficient or unknown")
   payload={"organization":m.meta(orgs[0]),"sourceStore":m.meta(source),"targetStore":m.meta(target),"description":req["description"],"externalCode":req["externalCode"],"applicable":True,"moment":dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).strftime("%Y-%m-%d %H:%M:%S"),"positions":[{"assortment":p["assortment"],"quantity":p["quantity"],"price":0} for p in mapping]}
   db.put(ROOT+"creation:v1",{"status":"inflight","externalCode":req["externalCode"],"started_at":m.now()})
   result.update(status="inflight",write_attempted=True);save(result)
   doc=t.request(m.MS,"entity/move","POST",payload)
   db.put(ROOT+"creation:v1",{"status":"created","id":doc["id"],"externalCode":req["externalCode"]})
 live=t.request(m.MS,"entity/move/"+doc["id"])
 positions=w.ms_rows("entity/move/"+doc["id"]+"/positions")
 checks={"positions":totals(positions)==expected,"quantity":sum(p["quantity"] for p in positions)==77,"posted":live.get("applicable") is True,"zero_prices":live.get("sum")==0 and all(p.get("price")==0 for p in positions),"source":m.href(live["sourceStore"])==m.href(source),"target":m.href(live["targetStore"])==m.href(target),"comment":live.get("description")==req["description"],"not_deleted":not live.get("deleted")}
 result.update(status="verified" if all(checks.values()) else "verification_failed",id=live["id"],name=live["name"],url=live["meta"].get("uuidHref"),quantity=sum(p["quantity"] for p in positions),positions=len(positions),description=live.get("description"),moment=live["moment"],checks=checks,verified_at=m.now());save(result)
 assert all(checks.values()),"Document verification failed"
 db.put(ROOT+"creation:v1",{"status":"verified","id":live["id"],"externalCode":req["externalCode"]})
 print(json.dumps({"status":"verified","quantity":77,"positions":len(positions)}))
except Exception as e:
 if result.get("status") not in ("needs_mapping","insufficient_stock","inflight","verification_failed"):result["status"]="stopped"
 result.update(error=str(e) if isinstance(e,(m.Stop,AssertionError)) else type(e).__name__,checked_at=m.now())
 save(result)
 print(json.dumps({"status":"stopped","write_attempted":result.get("write_attempted",False),"error_type":type(e).__name__}));raise SystemExit(1)
