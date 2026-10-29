"""Add the exact privately requested posted return to WB China seller inventory once."""
import os,json,time,collections,urllib.request,urllib.error
import fbs_document_chain as m
ROOT="returns_transfer:china:20261028:"
t=m.Transport();db=m.Cache(t);w=m.Worker(t,db,{})
req=db.get(ROOT+"fbs_request:v1")
def save(v):db.put(ROOT+"fbs_result:v1",v)
def wb(host,path,method="GET",body=None):
 assert (host,path,method) in [("marketplace-api.wildberries.ru","/api/v3/warehouses","GET"),("content-api.wildberries.ru","/content/v2/get/cards/list","POST")] or (host=="marketplace-api.wildberries.ru" and path=="/api/v3/stocks/"+str(req["warehouse_id"]) and method in ("POST","PUT"))
 request=urllib.request.Request("https://"+host+path,data=None if body is None else json.dumps(body).encode(),headers={"Authorization":os.environ["WB_TOKEN_3"],"Content-Type":"application/json"},method=method)
 try:
  with urllib.request.urlopen(request,timeout=60) as r:
   raw=r.read()
   return {"http_status":r.status,"body":json.loads(raw) if raw else None}
 except urllib.error.HTTPError as e:raise m.Stop("WB HTTP_"+str(e.code)+" "+method) from None
 except (TimeoutError,urllib.error.URLError):raise m.Stop("WB outcome uncertain "+method) from None
def stocks(ids):
 data=wb("marketplace-api.wildberries.ru","/api/v3/stocks/"+str(req["warehouse_id"]),"POST",{"chrtIds":ids})["body"]
 by={}
 for p in data["stocks"]:
  cid=p["chrtId"];assert cid in ids and cid not in by and type(p["amount"]) is int and p["amount"]>=0
  by[cid]=p["amount"]
 assert set(by)==set(ids),"Current seller stock coverage incomplete"
 return by
try:
 assert req["writes_enabled"] is True and req["cabinet"]=="token_3" and req["expected_quantity"]==77
 prior=db.get(ROOT+"fbs_result:v1")
 if prior and prior.get("status")=="verified":
  print(json.dumps({"status":"verified","duplicate_prevented":True}));raise SystemExit(0)
 assert not prior or not prior.get("write_attempted"),"Prior stock update outcome needs reconciliation; do not add twice"
 receipt=db.get(ROOT+"result:v1")
 assert receipt["status"]=="verified" and receipt["id"]==req["source_document_id"]
 doc=t.request(m.MS,"entity/move/"+req["source_document_id"])
 assert doc.get("applicable") is True and not doc.get("deleted")
 assert m.href(doc["targetStore"]).endswith("/3c67619d-f25d-11ee-0a80-0c6f000a027a")
 ps=w.ms_rows("entity/move/"+doc["id"]+"/positions",{"expand":"assortment"})
 expected=collections.Counter()
 for p in receipt["mapping"]:expected[m.href(p["assortment"])]+=p["quantity"]
 actual=collections.Counter();counts=collections.Counter();spelling={}
 for p in ps:
  assert p["quantity"]>0 and p["quantity"]==int(p["quantity"])
  actual[m.href(p["assortment"])]+=p["quantity"]
  article=p["assortment"]["article"].strip();key=article.casefold()
  counts[key]+=int(p["quantity"]);spelling[key]=article
 assert actual==expected and sum(counts.values())==77,"Posted return composition changed"
 save({"status":"mapping","write_attempted":False,"quantity":77,"source_document":{"id":doc["id"],"name":doc["name"],"updated":doc["updated"]}})
 whs=wb("marketplace-api.wildberries.ru","/api/v3/warehouses")["body"]
 wh=[p for p in whs if p["id"]==req["warehouse_id"] and p["name"]==req["warehouse_name"] and not p.get("isDeleting")]
 assert len(wh)==1,"Wrong seller warehouse"
 cards=[];cursor={"limit":100};seen=set()
 while True:
  answer=wb("content-api.wildberries.ru","/content/v2/get/cards/list","POST",{"settings":{"cursor":cursor,"filter":{"withPhoto":-1}}})["body"]
  cards+=answer["cards"]
  if answer["cursor"]["total"]<100:break
  c=answer["cursor"];marker=(c["updatedAt"],c["nmID"]);assert marker not in seen;seen.add(marker)
  cursor={"limit":100,"updatedAt":c["updatedAt"],"nmID":c["nmID"]};time.sleep(.7)
 by=collections.defaultdict(list)
 for p in cards:by[p["vendorCode"].strip().casefold()].append(p)
 mapped=[];issues=[]
 for article,quantity in counts.items():
  found=by[article]
  if len(found)!=1 or len(found[0]["sizes"])!=1:
   issues.append({"article":spelling[article],"quantity":quantity,"matches":[{"nmID":p["nmID"],"vendorCode":p["vendorCode"],"sizes":p["sizes"]} for p in found]});continue
  p=found[0];mapped.append({"article":spelling[article],"delta":quantity,"nmID":p["nmID"],"chrtId":p["sizes"][0]["chrtID"]})
 if issues:
  save({"status":"needs_mapping","write_attempted":False,"quantity":77,"issues":issues,"mapped":mapped});raise m.Stop("WB card missing or ambiguous")
 assert sum(p["delta"] for p in mapped)==77
 ids=[p["chrtId"] for p in mapped];assert len(ids)==len(set(ids))
 latest=t.request(m.MS,"entity/move/"+doc["id"])
 assert latest["updated"]==doc["updated"] and latest["applicable"] is True,"Source document changed before stock update"
 before=stocks(ids)
 changes=[{**p,"before":before[p["chrtId"]],"after":before[p["chrtId"]]+p["delta"]} for p in mapped]
 result={"status":"prepared","write_attempted":False,"warehouse":wh[0],"source_document":{"id":doc["id"],"name":doc["name"],"updated":doc["updated"]},"quantity_added":77,"positions":len(changes),"changes":changes,"prepared_at":m.now()}
 save(result)
 assert stocks(ids)==before,"Stock changed during preflight; recalculate before update"
 result.update(status="inflight",write_attempted=True,write_started_at=m.now());save(result)
 response=wb("marketplace-api.wildberries.ru","/api/v3/stocks/"+str(req["warehouse_id"]),"PUT",{"stocks":[{"chrtId":p["chrtId"],"amount":p["after"]} for p in changes]})
 assert response["http_status"]==204
 result.update(status="accepted",write_http_status=204);save(result)
 after=stocks(ids)
 for p in result["changes"]:p["verified_amount"]=after[p["chrtId"]]
 checks={"all_amounts_verified":all(after[p["chrtId"]]==p["after"] for p in changes),"quantity_added":sum(p["delta"] for p in changes)==77,"source_document_verified":True,"warehouse_identity":True}
 result.update(status="verified" if all(checks.values()) else "readback_mismatch",checks=checks,verified_at=m.now());save(result)
 assert all(checks.values()),"Stock readback mismatch; no blind retry"
 print(json.dumps({"status":"verified","quantity_added":77,"positions":len(changes)}))
except Exception as e:
 prior=db.get(ROOT+"fbs_result:v1") or {}
 attempted=prior.get("write_attempted",False)
 if not attempted and prior.get("status")!="needs_mapping":prior["status"]="preflight_failed"
 prior.update(write_attempted=attempted,error=str(e) if isinstance(e,(m.Stop,AssertionError)) else type(e).__name__,checked_at=m.now());save(prior)
 print(json.dumps({"status":"stopped","write_attempted":attempted,"error_type":type(e).__name__}));raise SystemExit(1)
