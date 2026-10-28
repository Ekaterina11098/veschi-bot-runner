"""Add only normal units from the private verified return batch to WB China seller stock."""
import os,json,re,time,collections,urllib.request,urllib.error
import fbs_document_chain as m
ROOT="returns_transfer:multi:20261027:batch2:"
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
 answer=wb("marketplace-api.wildberries.ru","/api/v3/stocks/"+str(req["warehouse_id"]),"POST",{"chrtIds":ids})["body"]
 by={}
 for row in answer["stocks"]:
  cid=row["chrtId"];assert cid not in by and cid in ids and type(row["amount"]) is int and row["amount"]>=0
  by[cid]=row["amount"]
 assert set(by)==set(ids),"Live stock response incomplete"
 return by
def norm(s):return s.strip().casefold().replace("c","с")
def product_code(item,source):
 match=re.fullmatch(r"(зонт|панама|манишка|ремень|шарф)\s*—\s*(\d+)",item)
 if match:return str(int(match[2]))+{"зонт":"з","панама":"м","манишка":"м","ремень":"р","шарф":"м"}[match[1]]
 number=re.match(r"^\d+",item).group()
 if number=="00":number="0"
 code=number+"с"
 return source.get("code_aliases",{}).get(code,code)
try:
 assert req["writes_enabled"] is True and req["cabinet"]=="token_3" and req["included_category"]=="Норм"
 prior=db.get(ROOT+"fbs_result:v1")
 if prior and prior.get("status")=="verified":
  print(json.dumps({"status":"verified","duplicate_prevented":True}));raise SystemExit(0)
 assert not prior or not prior.get("write_attempted"),"Prior write outcome needs reconciliation; do not add twice"
 source=db.get(ROOT+"request:v1");pre=db.get(ROOT+"preflight_fast:v1");receipts=db.get(ROOT+"result:v1")
 assert receipts["status"]=="verified" and len(receipts["sources"])==4
 bysource={s["slug"]:s for s in pre["sources"]}
 moves={s["slug"]:s for s in receipts["sources"]}
 normal=collections.Counter();held=collections.Counter();metadata={};observed=[]
 for s in source["sources"]:
  mapped=bysource[s["slug"]];bycode={norm(p["code"]):p for p in mapped["mapping"]}
  expected=collections.Counter({m.href(p["assortment"]):p["quantity"] for p in mapped["mapping"]})
  doc=t.request(m.MS,"entity/move/"+moves[s["slug"]]["id"])
  assert doc["applicable"] is True and not doc.get("deleted")
  assert m.href(doc["sourceStore"])==m.href(mapped["store"]) and m.href(doc["targetStore"])==m.href(pre["target"])
  ps=w.ms_rows("entity/move/"+doc["id"]+"/positions")
  actual=collections.Counter()
  for p in ps:actual[m.href(p["assortment"])]+=p["quantity"]
  assert actual==expected,"Transfer was changed after recorded category classification"
  observed.append({"id":doc["id"],"name":doc["name"],"updated":doc["updated"]})
  for row in s["rows"]:
   product=bycode[norm(product_code(row["item"],source))]
   article=product["article"].strip();metadata[article.casefold()]=article
   (normal if row["category"]==req["included_category"] else held)[article.casefold()]+=1
 assert sum(normal.values())==req["expected_normal_quantity"]==180
 assert sum(held.values())==req["expected_held_quantity"]==3
 skipped=collections.Counter()
 for article in req.get("skipped_normal_articles",[]):
  key=article.strip().casefold();assert key in normal
  skipped[key]=normal.pop(key)
 assert sum(skipped.values())==req["expected_skipped_normal_quantity"]==2
 assert sum(normal.values())==req["expected_added_quantity"]==178
 save({"status":"mapping","write_attempted":False,"requested_normal_quantity":180,"normal_quantity":178,"skipped_normal_quantity":2,"held_quantity":3,"moves":observed})
 warehouses=wb("marketplace-api.wildberries.ru","/api/v3/warehouses")["body"]
 chosen=[x for x in warehouses if x["id"]==req["warehouse_id"] and x["name"]==req["warehouse_name"] and not x.get("isDeleting")]
 assert len(chosen)==1,"Wrong WB seller warehouse"
 cards=[];cursor={"limit":100};seen=set()
 while True:
  answer=wb("content-api.wildberries.ru","/content/v2/get/cards/list","POST",{"settings":{"cursor":cursor,"filter":{"withPhoto":-1}}})["body"]
  cards+=answer["cards"]
  if answer["cursor"]["total"]<100:break
  c=answer["cursor"];marker=(c["updatedAt"],c["nmID"]);assert marker not in seen;seen.add(marker)
  cursor={"limit":100,"updatedAt":c["updatedAt"],"nmID":c["nmID"]};time.sleep(.7)
 byarticle=collections.defaultdict(list)
 for c in cards:byarticle[c["vendorCode"].strip().casefold()].append(c)
 mapping=[];issues=[];held_cards=[]
 for article,delta in normal.items():
  found=byarticle[article]
  if len(found)!=1 or len(found[0]["sizes"])!=1:
   issues.append({"article":metadata[article],"quantity":delta,"matches":[{"nmID":c["nmID"],"vendorCode":c["vendorCode"],"sizes":c["sizes"]} for c in found]});continue
  c=found[0];size=c["sizes"][0]
  mapping.append({"article":metadata[article],"delta":delta,"nmID":c["nmID"],"chrtId":size["chrtID"]})
 for article,quantity in held.items():
  found=byarticle[article]
  held_cards.append({"article":metadata[article],"quantity_not_added":quantity,"also_has_normal_units":article in normal})
 if issues:
  save({"status":"needs_mapping","write_attempted":False,"issues":issues,"mapped":mapping,"held":held_cards,"skipped_normal":[{"article":metadata[a],"quantity":q} for a,q in skipped.items()],"requested_normal_quantity":180,"normal_quantity":178,"skipped_normal_quantity":2});raise m.Stop("WB cards missing or ambiguous")
 ids=[p["chrtId"] for p in mapping];assert len(set(ids))==len(ids)
 for d in observed:
  current=t.request(m.MS,"entity/move/"+d["id"])
  assert current["updated"]==d["updated"] and current["applicable"] is True,"Source transfer changed before write"
 # Read fresh quantities only after all source verification and card mapping.
 before=stocks(ids)
 changes=[{**p,"before":before[p["chrtId"]],"after":before[p["chrtId"]]+p["delta"]} for p in mapping]
 result={"status":"prepared","write_attempted":False,"warehouse":chosen[0],"moves":observed,"changes":changes,"held":held_cards,"skipped_normal":[{"article":metadata[a],"quantity":q} for a,q in skipped.items()],"requested_normal_quantity":180,"normal_quantity":178,"skipped_normal_quantity":2,"held_quantity":3,"positions":len(changes),"prepared_at":m.now()}
 save(result)
 assert stocks(ids)==before,"Stock changed during preflight; recompute before writing"
 result.update(status="inflight",write_attempted=True,write_started_at=m.now());save(result)
 response=wb("marketplace-api.wildberries.ru","/api/v3/stocks/"+str(req["warehouse_id"]),"PUT",{"stocks":[{"chrtId":p["chrtId"],"amount":p["after"]} for p in changes]})
 assert response["http_status"]==204
 result.update(status="accepted",write_http_status=204);save(result)
 after=stocks(ids)
 for p in result["changes"]:p["verified_amount"]=after[p["chrtId"]]
 checks={"all_amounts_verified":all(after[p["chrtId"]]==p["after"] for p in changes),"added_only_normal":sum(p["delta"] for p in changes)==178,"held_units_excluded":sum(held.values())==3,"correct_warehouse":True,"all_four_source_moves_verified":len(observed)==4}
 result.update(status="verified" if all(checks.values()) else "readback_mismatch",checks=checks,verified_at=m.now());save(result)
 assert all(checks.values()),"Stock readback mismatch; no blind retry"
 print(json.dumps({"status":"verified","normal_added":178,"positions":len(changes),"held":3}))
except Exception as e:
 prior=db.get(ROOT+"fbs_result:v1") or {}
 attempted=prior.get("write_attempted",False)
 if not attempted and prior.get("status")!="needs_mapping":prior["status"]="preflight_failed"
 prior.update(write_attempted=attempted,error=str(e) if isinstance(e,(m.Stop,AssertionError)) else type(e).__name__,checked_at=m.now())
 save(prior)
 print(json.dumps({"status":"stopped","write_attempted":attempted,"error_type":type(e).__name__}));raise SystemExit(1)
