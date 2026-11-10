"""One authorized sequential return move; private input and journal, no WB calls."""
import collections,datetime as dt,re,math
import fbs_document_chain as m
ROOT="returns_transfer:china:20261110:evening:"
t=m.Transport();db=m.Cache(t);w=m.Worker(t,db,{})
r={"status":"mapping","write_attempted":False,"at":m.now()}
def save():db.put(ROOT+"result:v1",r)
def norm(s):return s.strip().casefold().replace("c","с")
def code(s):
 match=re.fullmatch(r"(зонт|панама|манишка|ремень|шарф)\s*—\s*(\d+)(?:\s*—.*)?",s)
 if match:return str(int(match[2]))+{"зонт":"з","панама":"м","манишка":"м","ремень":"р","шарф":"м"}[match[1]]
 match=re.fullmatch(r"(\d+)(?:\s*—.*)?",s)
 assert match,"Invalid private input"
 return ("0" if match[1]=="00" else match[1])+"с"
def totals(ps):
 out=collections.Counter()
 for p in ps:out[m.href(p["assortment"])]+=p["quantity"]
 return out
try:
 req=db.get(ROOT+"request:v1")
 assert req["writes_enabled"] is True and req["total"]==156 and len(req["items"])==79 and sum(x["quantity"] for x in req["items"])==156
 assert req["file_sha256"]=="6530bcede4d47b7471204f780a7d14845374477d9bd708b356bc3d33aebf2ae6"
 assert req["externalCode"]=="returns-china-20261110-evening-6530bcede4d47b74"
 stores=w.ms_rows("entity/store")
 def store(which):
  found=[x for x in stores if x["id"]==req[which+"_id"] and x["name"]==req[which+"_name"] and not x.get("archived")]
  assert len(found)==1,"Warehouse identity mismatch"
  return found[0]
 source=store("source");target=store("target")
 orgs=w.ms_rows("entity/organization");assert len(orgs)==1
 products=w.ms_rows("entity/product")
 mapping=[];issues=[]
 for item in req["items"]:
  key=code(item["label"])
  found=[p for p in products if not p.get("archived") and norm(p.get("code",""))==norm(key)]
  if not found and key.endswith("с"):
   found=[p for p in products if not p.get("archived") and re.fullmatch(r"\d+с",norm(p.get("code",""))) and int(norm(p["code"])[:-1])==int(key[:-1])]
  if len(found)!=1:
   issues.append({"item":item,"code":key,"issue":"mapping","candidates":[{k:p.get(k) for k in ("id","code","article","name")} for p in found]});continue
  p=found[0]
  assert not p.get("variantsCount") and not p.get("isSerialTrackable") and p.get("trackingType","NOT_TRACKED")=="NOT_TRACKED","Special product handling required"
  mapping.append({**item,"id":p["id"],"code":p.get("code"),"article":p.get("article"),"name":p["name"],"assortment":m.meta(p),"quantity":item["quantity"]})
 r.update(mapping=mapping,issues=issues)
 if issues:
  r["status"]="needs_mapping";save();raise m.Stop("Private mapping review required")
 positions=[{"assortment":p["assortment"],"quantity":p["quantity"],"price":0} for p in mapping]
 expected=totals(positions)
 docs=w.ms_rows("entity/move",{"filter":"externalCode="+req["externalCode"]})
 assert len(docs)<=1,"Duplicate external code"
 state=db.get(ROOT+"creation:v1")
 if docs:doc=docs[0]
 else:
  assert not state or state.get("status") not in ("inflight","created"),"Prior uncertain outcome; reconcile before retry"
  matching=[]
  for d in w.ms_rows("entity/move"):
   if d.get("deleted") or d.get("description")!=req["description"]:continue
   if m.href(d.get("sourceStore",{}))!=m.href(source) or m.href(d.get("targetStore",{}))!=m.href(target):continue
   if totals(w.ms_rows("entity/move/"+d["id"]+"/positions"))==expected:matching.append(d)
  assert len(matching)<=1,"Multiple matching documents"
  if matching:doc=matching[0]
  else:
   stock=t.request(m.MS,"report/stock/bystore/current",params={"stockType":"freeStock","include":"zeroLines"})
   assert isinstance(stock,list)
   index={}
   for row in stock:
    pair=(row["storeId"],row["assortmentId"])
    assert pair not in index
    index[pair]=row["freeStock"]
   needed=collections.Counter()
   for p in mapping:needed[p["id"]]+=p["quantity"]
   issues=[]
   for ident,quantity in needed.items():
    available=index.get((source["id"],ident))
    p=next(x for x in mapping if x["id"]==ident)
    if type(available) not in (int,float) or not math.isfinite(available) or available<quantity:
     issues.append({"code":p["code"],"article":p["article"],"required":quantity,"available":available})
   r.update(status="insufficient_stock" if issues else "prepared",issues=issues,stock_checked_at=m.now());save()
   if issues:raise m.Stop("Source availability insufficient or unknown")
   payload={"organization":m.meta(orgs[0]),"sourceStore":m.meta(source),"targetStore":m.meta(target),"description":req["description"],"externalCode":req["externalCode"],"applicable":True,"moment":dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).strftime("%Y-%m-%d %H:%M:%S"),"positions":positions}
   assert db.claim(ROOT+"creation_claim:v1",{"started_at":m.now(),"externalCode":req["externalCode"],"file_sha256":req["file_sha256"]}),"Creation already claimed; reconcile instead of repeat"
   db.put(ROOT+"creation:v1",{"status":"inflight","at":m.now(),"externalCode":req["externalCode"]})
   r.update(status="inflight",write_attempted=True);save()
   doc=t.request(m.MS,"entity/move","POST",payload)
   db.put(ROOT+"creation:v1",{"status":"created","id":doc["id"]})
 live=t.request(m.MS,"entity/move/"+doc["id"])
 actual=w.ms_rows("entity/move/"+doc["id"]+"/positions")
 checks={"order": [m.href(p["assortment"]) for p in actual]==[m.href(p["assortment"]) for p in positions],"row_quantities":[p["quantity"] for p in actual]==[p["quantity"] for p in positions],"positions":len(actual)==79,"quantity":sum(p["quantity"] for p in actual)==156,"zero_prices":live.get("sum")==0 and all(p.get("price")==0 for p in actual),"posted":live.get("applicable") is True,"source":m.href(live["sourceStore"])==m.href(source),"target":m.href(live["targetStore"])==m.href(target),"comment":live.get("description")==req["description"],"not_deleted":not live.get("deleted")}
 r.update(status="verified" if all(checks.values()) else "verification_failed",id=live["id"],name=live["name"],url=live["meta"].get("uuidHref"),checks=checks,quantity=sum(p["quantity"] for p in actual),positions=len(actual),verified_at=m.now());save()
 assert all(checks.values()),"Readback verification failed"
 db.put(ROOT+"creation:v1",{"status":"verified","id":live["id"]})
 print("Authorized move verified; order and zero prices confirmed")
except Exception as e:
 if r["status"] not in ("needs_mapping","insufficient_stock","inflight","verification_failed"):r["status"]="stopped"
 r["error"]=str(e) if isinstance(e,(m.Stop,AssertionError)) else type(e).__name__
 save()
 print("Stopped; review private journal; no automatic write replay")
 raise SystemExit(1)
