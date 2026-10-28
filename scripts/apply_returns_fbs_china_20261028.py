"""Add corrected transfer quantities only to explicitly selected China FBS stock."""
import os,json,collections,time,urllib.request,urllib.error
import fbs_document_chain as m
ROOT="returns_transfer:china:20261027:"
t=m.Transport();db=m.Cache(t);w=m.Worker(t,db,{})
def wb(path,method="GET",body=None):
 assert path=="/api/v3/warehouses" and method=="GET" or path=="/api/v3/stocks/"+str(req["warehouse_id"]) and method in ("POST","PUT")
 request=urllib.request.Request("https://marketplace-api.wildberries.ru"+path,data=None if body is None else json.dumps(body).encode(),headers={"Authorization":os.environ["WB_TOKEN_3"],"Content-Type":"application/json"},method=method)
 try:
  with urllib.request.urlopen(request,timeout=60) as r:
   raw=r.read()
   return {"http_status":r.status,"body":json.loads(raw) if raw else None}
 except urllib.error.HTTPError as e:raise m.Stop("WB HTTP_"+str(e.code)+" "+method) from None
 except (TimeoutError,urllib.error.URLError):raise m.Stop("WB outcome uncertain "+method) from None
def put(value):db.put(ROOT+"fbs_result:v1",value)
def current(ids):
 reply=wb("/api/v3/stocks/"+str(req["warehouse_id"]),"POST",{"chrtIds":ids})
 rows=reply["body"]["stocks"];d={}
 for r in rows:
  cid=r["chrtId"];assert cid not in d and cid in ids and type(r["amount"]) is int and r["amount"]>=0,"Stock row invalid"
  d[cid]=r["amount"]
 assert set(d)==set(ids),"Stock response incomplete"
 return d
req=db.get(ROOT+"fbs_request:v1")
try:
 assert req["writes_enabled"] is True and req["cabinet"]=="token_3"
 prior=db.get(ROOT+"fbs_result:v1")
 if prior and prior.get("status")=="verified":
  print(json.dumps({"status":"verified","duplicate_prevented":True}));raise SystemExit(0)
 assert not prior or prior.get("status") in ("preflight_failed",),"Prior write outcome requires read-only reconciliation"
 preview=db.get(ROOT+"fbs_preview:v1")
 assert preview["status"]=="mapped" and not preview["issues"]
 d=t.request(m.MS,"entity/move/"+req["source_document_id"])
 assert d["applicable"] is True and not d.get("deleted")
 assert d["updated"]==preview["move"]["updated"],"Corrected transfer changed after mapping"
 assert m.href(d["targetStore"]).endswith("/3c67619d-f25d-11ee-0a80-0c6f000a027a")
 ps=w.ms_rows("entity/move/"+d["id"]+"/positions",{"expand":"assortment"})
 counts=collections.Counter()
 for p in ps:
  assert p["quantity"]>0 and p["quantity"]==int(p["quantity"])
  counts[p["assortment"]["article"].strip().casefold()]+=int(p["quantity"])
 expected=collections.Counter({r["article"].casefold():r["delta"] for r in preview["mapping"]})
 assert counts==expected,"Current corrected document and mapped quantities differ"
 excluded={x.casefold() for x in req["excluded_articles"]}
 mapping=[x for x in preview["mapping"] if x["article"].casefold() not in excluded]
 omitted=[x for x in preview["mapping"] if x["article"].casefold() in excluded]
 assert len(mapping)==87 and sum(x["delta"] for x in mapping)==194
 assert len(omitted)==3 and sum(x["delta"] for x in omitted)==16
 whs=wb("/api/v3/warehouses")["body"]
 found=[x for x in whs if x["id"]==req["warehouse_id"] and x["name"]==req["warehouse_name"] and not x.get("isDeleting")]
 assert len(found)==1,"Warehouse identity mismatch"
 ids=[x["chrtId"] for x in mapping];allids=ids+[x["chrtId"] for x in omitted]
 assert len(set(allids))==len(allids)
 before=current(allids)
 changes=[{**x,"before":before[x["chrtId"]],"after":before[x["chrtId"]]+x["delta"]} for x in mapping]
 result={"status":"prepared","move":preview["move"],"warehouse":found[0],"quantity_added":194,"positions":87,"changes":changes,"excluded":[{**x,"before":before[x["chrtId"]]} for x in omitted],"prepared_at":m.now(),"write_attempted":False}
 put(result)
 # Fresh read immediately before writing prevents overwriting an intervening stock change.
 assert current(allids)==before,"Stock changed during preflight; prepare again"
 latest=t.request(m.MS,"entity/move/"+d["id"])
 assert latest["updated"]==d["updated"] and latest["applicable"] is True,"Source document changed before write"
 result.update(status="inflight",write_attempted=True,write_started_at=m.now());put(result)
 answer=wb("/api/v3/stocks/"+str(req["warehouse_id"]),"PUT",{"stocks":[{"chrtId":x["chrtId"],"amount":x["after"]} for x in changes]})
 assert answer["http_status"]==204,"Unexpected stock write response"
 result.update(status="accepted",write_http_status=204);put(result)
 after=current(allids)
 checks={"all_target_values":all(after[x["chrtId"]]==x["after"] for x in changes),"excluded_not_in_write":not ({x["chrtId"] for x in omitted}&set(ids)),"quantity_added":sum(x["after"]-x["before"] for x in changes)==194,"corrected_source":True,"warehouse_identity":True}
 for x in result["changes"]:x["verified_amount"]=after[x["chrtId"]]
 for x in result["excluded"]:x["after"]=after[x["chrtId"]]
 result.update(status="verified" if all(checks.values()) else "readback_mismatch",checks=checks,verified_at=m.now())
 put(result)
 assert all(checks.values()),"Readback differs; no blind retry"
 print(json.dumps({"status":"verified","quantity_added":194,"positions":87,"excluded_positions":3}))
except Exception as e:
 prior=db.get(ROOT+"fbs_result:v1") or {}
 attempted=prior.get("write_attempted",False)
 prior.update(status=prior.get("status") if attempted else "preflight_failed",error=str(e) if isinstance(e,(m.Stop,AssertionError)) else type(e).__name__,checked_at=m.now())
 put(prior)
 print(json.dumps({"status":"stopped","write_attempted":attempted,"error_type":type(e).__name__}));raise SystemExit(1)
