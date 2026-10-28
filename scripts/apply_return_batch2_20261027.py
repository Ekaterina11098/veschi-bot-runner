"""Create only requested source transfers whose full available stock was verified."""
import collections,json,datetime as dt,math,os,urllib.request,urllib.parse,urllib.error,gzip,time
import fbs_document_chain as m
ROOT="returns_transfer:multi:20261027:batch2:"
class StockTransport(m.Transport):
 def _request_once(self,base,path,method="GET",body=None,params=None):
  if base!=m.MS or path!="report/stock/all" or method!="GET":
   return super()._request_once(base,path,method,body,params)
  request=urllib.request.Request(base+path+"?"+urllib.parse.urlencode(params or {}),headers={"Authorization":"Bearer "+os.environ["MOYSKLAD_API_TOKEN"],"Accept":"application/json;charset=utf-8","Accept-Encoding":"gzip"})
  try:
   with urllib.request.urlopen(request,timeout=120) as r:
    raw=r.read()
    return json.loads(gzip.decompress(raw) if r.headers.get("Content-Encoding")=="gzip" else raw)
  except urllib.error.HTTPError as e:raise m.Stop("HTTP_"+str(e.code)+" GET report/stock/all") from None
  except (TimeoutError,urllib.error.URLError):raise m.Stop("API transport outcome uncertain") from None
t=StockTransport();db=m.Cache(t);w=m.Worker(t,db,{})
req=db.get(ROOT+"request:v1");pre=db.get(ROOT+"preflight_fast:v1")
assert req["writes_enabled"] is True
assert pre and pre["status"] in ("ready","needs_review")
assert len(pre["sources"])==4 and sum(s["quantity"] for s in pre["sources"])==183
orgs=w.ms_rows("entity/organization");assert len(orgs)==1
org=orgs[0];target=pre["target"]
summary={"status":"processing","sources":[],"at":m.now()}
def totals(ps):
 out=collections.Counter()
 for p in ps:out[m.href(p["assortment"])]+=p["quantity"]
 return out
for s in pre["sources"]:
 record={"label":s["label"],"slug":s["slug"],"quantity":s["quantity"]}
 if s["issues"]:
  record.update(status="blocked",issues=s["issues"]);summary["sources"].append(record);db.put(ROOT+"result:v1",summary);continue
 key=ROOT+"source:"+s["slug"]+":v1"
 ext=req["batch"]+":"+s["slug"]
 try:
  expected=collections.Counter({m.href(p["assortment"]):p["quantity"] for p in s["mapping"]})
  docs=w.ms_rows("entity/move",{"filter":"externalCode="+ext})
  assert len(docs)<=1,"Duplicate transfer identity"
  previous=db.get(key)
  if docs:doc=docs[0]
  else:
   assert not previous or previous.get("status") not in ("inflight","created"),"Prior creation outcome must be reconciled"
   # Same comment can legitimately contain the earlier, different return batch.
   candidates=w.ms_rows("entity/move",{"filter":"sourceStore="+m.href(s["store"])+";targetStore="+m.href(target)})
   same=[]
   for d in candidates:
    if d.get("deleted") or d["id"] in req.get("exclude_existing_ids",[]):continue
    if (d.get("description") or "").strip().casefold()!=s["description"].strip().casefold():continue
    positions=w.ms_rows("entity/move/"+d["id"]+"/positions")
    if totals(positions)==expected:same.append(d)
   assert len(same)<=1,"Multiple matching manual documents"
   if same:doc=same[0]
   else:
    live=t.request(m.MS,"report/stock/bystore/current",params={"stockType":"freeStock","include":"zeroLines"})
    assert isinstance(live,list),"Short availability report incomplete"
    by={}
    for row in live:
     pair=(row["storeId"],row["assortmentId"])
     assert pair not in by,"Duplicate availability row"
     by[pair]=row["freeStock"]
    shortages=[]
    for p in s["mapping"]:
     pair=(s["store"]["id"],p["id"])
     assert pair in by,"Fresh available stock unknown"
     a=by[pair];assert type(a) in (int,float) and math.isfinite(a)
     if a<p["quantity"]:shortages.append({"code":p["code"],"article":p["article"],"required":p["quantity"],"available":a})
    if shortages:
     record.update(status="blocked",issues=shortages);db.put(key,record);summary["sources"].append(record);db.put(ROOT+"result:v1",summary);continue
    payload={"organization":m.meta(org),"sourceStore":m.meta(s["store"]),"targetStore":m.meta(target),"description":s["description"],"externalCode":ext,"applicable":True,"moment":dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).strftime("%Y-%m-%d %H:%M:%S"),"positions":[{"assortment":p["assortment"],"quantity":p["quantity"],"price":0} for p in s["mapping"]]}
    db.put(key,{"status":"inflight","externalCode":ext,"started_at":m.now()})
    doc=t.request(m.MS,"entity/move","POST",payload)
    db.put(key,{"status":"created","id":doc["id"],"externalCode":ext})
  live=t.request(m.MS,"entity/move/"+doc["id"])
  positions=w.ms_rows("entity/move/"+doc["id"]+"/positions")
  checks={"positions":totals(positions)==expected,"quantity":sum(p["quantity"] for p in positions)==s["quantity"],"posted":live.get("applicable") is True,"zero_prices":live.get("sum")==0 and all(p.get("price")==0 for p in positions),"source":m.href(live["sourceStore"])==m.href(s["store"]),"target":m.href(live["targetStore"])==m.href(target),"comment":live.get("description")==s["description"],"not_deleted":not live.get("deleted")}
  record.update(status="verified" if all(checks.values()) else "verification_failed",id=live["id"],name=live["name"],url=live["meta"].get("uuidHref"),checks=checks,positions=len(positions),verified_at=m.now())
  db.put(key,record)
  assert all(checks.values()),"Readback verification failed"
 except Exception as e:
  record.update(status="stopped",error=str(e) if isinstance(e,(m.Stop,AssertionError)) else type(e).__name__)
 summary["sources"].append(record);db.put(ROOT+"result:v1",summary)
summary["status"]="verified" if all(s["status"]=="verified" for s in summary["sources"]) else "needs_review"
summary["completed_at"]=m.now();db.put(ROOT+"result:v1",summary)
print(json.dumps({"status":summary["status"],"verified":sum(s["status"]=="verified" for s in summary["sources"]),"blocked":sum(s["status"]!="verified" for s in summary["sources"])}))
