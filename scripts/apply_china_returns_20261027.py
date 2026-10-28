"""Create only the specifically requested private returns transfer, then verify it."""
import collections,datetime as dt,json,hashlib
import fbs_document_chain as m
ROOT="returns_transfer:china:20261027:"
t=m.Transport();db=m.Cache(t);w=m.Worker(t,db,{})
req=db.get(ROOT+"request:v1")
def key(row):
 if " — " not in row:return req.get("code_overrides",{}).get(row,row+"с")
 word,n=row.split(" — ")
 return str(int(n))+{"зонт":"з","панама":"м","шарф":"м","манишка":"м","ремень":"р"}[word]
def norm(code):return code.strip().casefold().replace("c","с")
def report(value):db.put(ROOT+"result:v1",value)
try:
 assert req["writes_enabled"] is True and len(req["rows"])==req["quantity"]==210
 counts=collections.Counter(norm(key(x)) for x in req["rows"])
 products=w.ms_rows("entity/product")
 by=collections.defaultdict(list)
 for p in products:
  if not p.get("archived"):by[norm(p.get("code",""))].append(p)
 mapping=[]
 for code,quantity in counts.items():
  assert len(by[code])==1,"Product mapping missing or ambiguous"
  p=by[code][0]
  mapping.append({"key":code,"id":p["id"],"article":p.get("article"),"name":p["name"],"quantity":quantity,"assortment":m.meta(p)})
 assert sum(x["quantity"] for x in mapping)==210
 source=t.request(m.MS,"entity/store/"+req["sourceStore"])
 target=t.request(m.MS,"entity/store/"+req["targetStore"])
 org=t.request(m.MS,"entity/organization/"+req["organization"])
 assert source["name"]=="Гонконг WB FBO" and target["name"]=="МСК"
 assert not source.get("archived") and not target.get("archived")
 documents=w.ms_rows("entity/move")
 existing=[d for d in documents if d.get("externalCode")==req["externalCode"]]
 similar=[d for d in documents if (d.get("description") or "").strip().casefold()==req["description"].strip().casefold() and d.get("externalCode")!=req["externalCode"]]
 assert not similar,"Matching comment already exists; reconcile before creating"
 assert len(existing)<=1,"Duplicate external identity"
 payload={"organization":m.meta(org),"sourceStore":m.meta(source),"targetStore":m.meta(target),"description":req["description"],"externalCode":req["externalCode"],"applicable":True,"moment":dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).strftime("%Y-%m-%d %H:%M:%S"),"positions":[{"assortment":x["assortment"],"quantity":x["quantity"],"price":0} for x in mapping]}
 report({"status":"prepared","quantity":210,"positions":len(mapping),"mapping":mapping})
 state=db.get(ROOT+"creation:v1")
 if existing:
  document=existing[0]
 else:
  assert not state or state.get("status")=="not_started","Prior creation outcome requires reconciliation"
  db.put(ROOT+"creation:v1",{"status":"inflight","externalCode":req["externalCode"],"started_at":m.now()})
  document=t.request(m.MS,"entity/move","POST",payload)
  db.put(ROOT+"creation:v1",{"status":"created","id":document["id"],"externalCode":req["externalCode"]})
 live=t.request(m.MS,"entity/move/"+document["id"])
 ps=w.ms_rows("entity/move/"+document["id"]+"/positions")
 expected=collections.Counter({m.href(x["assortment"]):x["quantity"] for x in mapping})
 actual=collections.Counter()
 for p in ps:actual[m.href(p["assortment"])]+=p["quantity"]
 checks={"positions":actual==expected,"quantity":sum(p["quantity"] for p in ps)==210,"posted":live.get("applicable") is True,"zero_prices":live.get("sum")==0 and all(p.get("price")==0 for p in ps),"comment":live.get("description")==req["description"],"source":m.href(live["sourceStore"])==m.href(source),"target":m.href(live["targetStore"])==m.href(target),"organization":m.href(live["organization"])==m.href(org),"not_deleted":not live.get("deleted"),"unique_document":len(w.ms_rows("entity/move",{"filter":"externalCode="+req["externalCode"]}))==1}
 result={"status":"verified" if all(checks.values()) else "verification_failed","id":live["id"],"name":live["name"],"moment":live["moment"],"quantity":sum(p["quantity"] for p in ps),"positions":len(ps),"sum":live.get("sum"),"description":live.get("description"),"source":source["name"],"target":target["name"],"checks":checks,"mapping":mapping,"verified_at":m.now(),"url":live.get("meta",{}).get("uuidHref")}
 report(result)
 assert all(checks.values()),"Document verification mismatch"
 db.put(ROOT+"creation:v1",{"status":"verified","id":live["id"],"externalCode":req["externalCode"]})
 print(json.dumps({"status":"verified","quantity":210,"positions":len(ps)}))
except Exception as e:
 previous=db.get(ROOT+"result:v1") or {}
 previous.update(status="stopped",error=str(e) if isinstance(e,(m.Stop,AssertionError)) else type(e).__name__,checked_at=m.now())
 report(previous)
 print(json.dumps({"status":"stopped","error_type":type(e).__name__}))
 raise SystemExit(1)
