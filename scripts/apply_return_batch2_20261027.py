"""Create only requested source transfers whose full available stock was verified."""
import collections,json,datetime as dt,math
import fbs_document_chain as m
ROOT="returns_transfer:multi:20261027:batch2:"
t=m.Transport();db=m.Cache(t);w=m.Worker(t,db,{})
req=db.get(ROOT+"request:v1");pre=db.get(ROOT+"preflight:v1")
assert req["writes_enabled"] is True
assert pre and pre["status"] in ("ready","needs_review")
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
    live=w.ms_rows("report/stock/all",{"filter":"store="+m.href(s["store"])+";stockMode=all;quantityMode=all"})
    by=collections.defaultdict(list)
    for r in live:by[(r.get("article") or "").strip().casefold()].append(r)
    shortages=[]
    for p in s["mapping"]:
     rows=by[(p["article"] or "").strip().casefold()]
     if len(rows)!=1:raise m.Stop("Fresh available stock unknown")
     r=rows[0];a=r.get("stock");v=r.get("reserve")
     assert all(type(x) in (int,float) and math.isfinite(x) for x in (a,v)) and v>=0
     if a-v<p["quantity"]:shortages.append({"code":p["code"],"article":p["article"],"required":p["quantity"],"available":a-v})
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
