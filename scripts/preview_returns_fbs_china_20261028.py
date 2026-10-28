"""Read the corrected transfer and current China FBS stock; no marketplace writes."""
import os,json,collections,hashlib,time,urllib.request,urllib.error
import fbs_document_chain as m
ROOT="returns_transfer:china:20261027:"
t=m.Transport();db=m.Cache(t);w=m.Worker(t,db,{})
def wb(host,path,method="GET",body=None):
 assert (host,path,method) in [("marketplace-api.wildberries.ru","/api/v3/warehouses","GET"),("content-api.wildberries.ru","/content/v2/get/cards/list","POST")] or (host=="marketplace-api.wildberries.ru" and path.startswith("/api/v3/stocks/") and method=="POST")
 req=urllib.request.Request("https://"+host+path,data=None if body is None else json.dumps(body).encode(),headers={"Authorization":os.environ["WB_TOKEN_3"],"Content-Type":"application/json"},method=method)
 try:
  with urllib.request.urlopen(req,timeout=60) as r:return json.load(r)
 except urllib.error.HTTPError as e:raise m.Stop("WB read HTTP_"+str(e.code)) from None
def run():
 old=db.get(ROOT+"result:v1");uid=old["id"]
 d=t.request(m.MS,"entity/move/"+uid)
 assert d["applicable"] is True and not d.get("deleted")
 assert m.href(d["sourceStore"]).endswith("/"+db.get(ROOT+"request:v1")["sourceStore"]) and m.href(d["targetStore"]).endswith("/"+db.get(ROOT+"request:v1")["targetStore"])
 ps=w.ms_rows("entity/move/"+uid+"/positions",{"expand":"assortment"})
 counts=collections.Counter()
 for p in ps:
  q=p["quantity"];a=(p["assortment"].get("article") or "").strip()
  assert a and q>0 and q==int(q)
  counts[a]+=int(q)
 warehouses=wb("marketplace-api.wildberries.ru","/api/v3/warehouses")
 configured=os.environ.get("WB_STOCK_WAREHOUSE_3","")
 snapshot={"status":"reading","move":{"id":uid,"name":d["name"],"updated":d["updated"],"description":d.get("description"),"quantity":sum(counts.values()),"positions":len(ps)},"warehouses":warehouses,"configured_warehouse":configured}
 db.put(ROOT+"fbs_preview:v1",snapshot)
 cards=[];cursor={"limit":100};seen=set()
 while True:
  page=wb("content-api.wildberries.ru","/content/v2/get/cards/list","POST",{"settings":{"cursor":cursor,"filter":{"withPhoto":-1}}})
  part=page["cards"];cards+=part
  if page["cursor"]["total"]<100:break
  c=page["cursor"];marker=(c["updatedAt"],c["nmID"]);assert marker not in seen;seen.add(marker)
  cursor={"limit":100,"updatedAt":c["updatedAt"],"nmID":c["nmID"]};time.sleep(.7)
 by=collections.defaultdict(list)
 for c in cards:by[c["vendorCode"].strip().casefold()].append(c)
 mapping=[];issues=[]
 for article,delta in counts.items():
  found=by[article.casefold()]
  if len(found)!=1 or len(found[0]["sizes"])!=1:
   issues.append({"article":article,"delta":delta,"matches":[{"nmID":c["nmID"],"article":c["vendorCode"],"sizes":c["sizes"]} for c in found]});continue
  c=found[0];size=c["sizes"][0]
  mapping.append({"article":article,"nmID":c["nmID"],"chrtId":size["chrtID"],"skus":size["skus"],"delta":delta})
 snapshot.update(status="mapped" if not issues else "needs_mapping",mapping=mapping,issues=issues,observed_at=m.now())
 active=[x for x in warehouses if not x.get("isDeleting") and (str(x["id"])==configured if configured else True)]
 if len(active)==1:
  wh=active[0];snapshot["warehouse"]=wh
  answer=wb("marketplace-api.wildberries.ru","/api/v3/stocks/"+str(wh["id"]),"POST",{"chrtIds":[x["chrtId"] for x in mapping]})
  snapshot["stocks"]=answer
 else:snapshot["warehouse_candidates"]=active
 db.put(ROOT+"fbs_preview:v1",snapshot)
 print(json.dumps({"status":snapshot["status"],"quantity":sum(counts.values()),"mapped":len(mapping),"issues":len(issues),"warehouse_selected":"warehouse" in snapshot}))
try:run()
except Exception as e:
 prior=db.get(ROOT+"fbs_preview:v1") or {}
 prior.update(status="stopped",error=str(e) if isinstance(e,(m.Stop,AssertionError)) else type(e).__name__)
 db.put(ROOT+"fbs_preview:v1",prior)
 print(json.dumps({"status":"stopped","error_type":type(e).__name__}));raise SystemExit(1)
