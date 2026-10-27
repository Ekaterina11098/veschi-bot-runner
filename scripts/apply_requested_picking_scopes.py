"""Apply an explicitly approved private picking reconciliation, without blind create retries."""
import os,json,collections,copy
import fbs_document_chain as m
t=m.Transport();db=m.Cache(t);reader=m.Worker(t,db,{})
root=os.environ["PICKING_REVIEW_ROOT"];req=db.get(root+"request:v1");audit=db.get(root+"audit:v1")
assert req.get("authorized_create") is True and req.get("mode")=="apply"
assert audit["status"]=="audited"
def counts(ps):
 result=collections.Counter()
 for p in ps:result[(p["assortment"].get("article") or "").strip().casefold()]+=p["quantity"]
 return dict(result)
def positions(path):return reader.ms_rows(path+"/positions",{"expand":"assortment"})
index={}
for p in reader.ms_rows("entity/product",{"filter":"archived=false"}):
 if isinstance(p.get("article"),str):index.setdefault(p["article"].strip().casefold(),[]).append(p)
def make_positions(expected):
 result=[]
 for article,q in sorted(expected.items()):
  products=index.get(article,[])
  assert len(products)==1 and not products[0].get("variantsCount") and not products[0].get("isSerialTrackable")
  p=products[0];assert p.get("trackingType","NOT_TRACKED")=="NOT_TRACKED"
  result.append({"quantity":q,"price":0,"discount":0,"vat":0,"vatEnabled":False,"assortment":m.meta(p)})
 return result
# Detect separate manual adjustments before increasing an existing demand.
targets=set()
known={d["id"] for chain in audit["chains"] for d in chain["documents"]}
for chain in audit["chains"]:
 for d in chain["documents"]:targets.update(d["missing"])
manual=[]
for d in reader.ms_rows("entity/demand",{"filter":"moment>=2026-10-26 00:00:00"}):
 if d["id"] in known or d.get("deleted") or not d.get("applicable") or (d.get("externalCode") or "").startswith("fbs-"):continue
 matches={a:q for a,q in counts(positions("entity/demand/"+d["id"])).items() if a in targets}
 if matches:manual.append({"id":d["id"],"name":d["name"],"description":d.get("description"),"counts":matches})
db.put(root+"manual_adjustment_check:v1",{"at":m.now(),"candidates":manual})
out={"at":m.now(),"status":"processing","chains":[],"manual_candidates":manual}
for chain in audit["chains"]:
 cabinet=chain["cabinet"];sid=chain["supply_id"];prefix="fbs_document_chain:"+cabinet+":"
 key=prefix+"supply:v1:"+sid;state=db.get(key)
 result={"cabinet":cabinet,"supply_id":sid,"before":chain["documents"]}
 try:
  c=db.get(prefix+"config:v1");assert c.get("writes_enabled") and c.get("status")=="active"
  expected=chain["expected"];wanted=make_positions(expected);scope=chain["scope"]
  missing={a for d in chain["documents"] for a in d["missing"]}
  if any(missing.intersection(x["counts"]) for x in manual):raise m.Stop("Possible separate manual correction; clarify before adding item")
  if cabinet=="china":
   w=m.Worker(t,db,c)
   raw=t.request(m.WB,"api/marketplace/v3/supplies/"+sid+"/order-ids")["orderIds"]
   assert set(raw)==set(scope["order_ids"])
   current=t.request(m.WB,"api/v3/supplies/"+sid);assert current.get("done") is True
   annotation=w.order_annotation(state["supply"])
   order_name=sid
  else:
   from fbs_ozon_chain import OzonWorker,snapshot
   current_scope=snapshot(state["act"])
   assert current_scope["ready"] and current_scope["counts"]==expected
   assert set(current_scope["included"])==set(scope["order_ids"])
   w=OzonWorker(t,db,c,state["act"],current_scope)
   annotation=w.order_annotation(state["supply"]);order_name=w.order_name
   state["picking_scope"]=current_scope
  # Preserve the original journal before any reconciliation.
  backup=root+"state_before:"+sid
  if not db.get(backup):db.put(backup,copy.deepcopy(state))
  extprefix=c.get("document_prefix","fbs-china")
  # Clear an old uncertain create only after fresh exact, manual and linked searches.
  if state.get("inflight"):
   typ=state["inflight"];ext=extprefix+":"+sid+":"+typ
   exact=w.ms_rows("entity/"+typ,{"filter":"externalCode="+ext})
   assert len(exact)<=1
   if not exact:
    assert not [d for d in chain["documents"] if d["type"]==typ and not d.get("deleted")]
    manual_orders=w.ms_rows("entity/customerorder",{"filter":"name="+order_name})
    assert not [d for d in manual_orders if cabinet=="china" or any(n in (d.get("description") or "") for n in scope["order_ids"])]
    assert typ=="customerorder"
    state["uncertain_create_reconciled"]={"at":m.now(),"type":typ,"no_existing_document":True}
    state.pop("inflight",None);db.put(key,state)
  state["positions"]=wanted;state["order_ids"]=sorted(scope["order_ids"])
  links={};result["documents"]=[]
  for typ in m.TYPES:
   payload=copy.deepcopy(c["templates"][typ])
   payload.update(positions=wanted,applicable=True,description=annotation["description"],
     moment=m.stamp(state["supply"]["closedAt"]).astimezone(m.dt.timezone(m.dt.timedelta(hours=3))).strftime("%Y-%m-%d %H:%M:%S"))
   if typ=="customerorder":payload["name"]=order_name
   elif typ=="demand":payload["customerOrder"]=links["customerorder"]
   else:payload["demand"]=links["demand"]
   ext=extprefix+":"+sid+":"+typ
   found=w.ms_rows("entity/"+typ,{"filter":"externalCode="+ext});assert len(found)<=1
   if found:
    d=found[0];assert not d.get("deleted")
    assert all(m.href(d.get(k,{}))==m.href(payload[k]) for k in ("organization","agent","store"))
    path="entity/"+typ+"/"+d["id"];oldps=positions(path)
    baseline=next((x for x in chain["documents"] if x["type"]==typ and x["id"]==d["id"]),None)
    assert counts(oldps)==expected or (baseline and counts(oldps)==baseline["counts"])
    if counts(oldps)!=expected or not d.get("applicable") or d.get("sum")!=0 or d.get("description")!=payload["description"] or any(p["price"]!=0 for p in oldps):
     oldids={m.href(p["assortment"]):p["id"] for p in oldps}
     newps=[dict(p,**({"id":oldids[m.href(p["assortment"])]} if m.href(p["assortment"]) in oldids else {})) for p in wanted]
     t.request(m.MS,path,"PUT",{"positions":newps,"description":payload["description"],"applicable":True})
   links[typ]=w.ensure(typ,payload,state,key)
   ref=state["documents"][typ]
   result["documents"].append({"type":typ,"id":ref["id"],"name":ref["name"]})
  orderpath="entity/customerorder/"+state["documents"]["customerorder"]["id"]
  order=t.request(m.MS,orderpath)
  if m.href(order.get("state",{}))!=m.href(annotation["state"]):
   t.request(m.MS,orderpath,"PUT",annotation)
  # Independent readback of complete chain; zero prices and linked basis required.
  for typ in m.TYPES:
   path="entity/"+typ+"/"+state["documents"][typ]["id"]
   doc=t.request(m.MS,path)
   payload=copy.deepcopy(c["templates"][typ]);payload.update(positions=wanted,description=annotation["description"])
   if typ=="demand":payload["customerOrder"]=links["customerorder"]
   if typ=="salesreturn":payload["demand"]=links["demand"]
   w.verify(typ,doc,payload)
   assert counts(positions(path))==expected
   if typ=="customerorder":assert m.href(doc.get("state",{}))==m.href(annotation["state"])
  state.update(status="complete",completed_at=m.now(),positions=wanted,order_ids=sorted(scope["order_ids"]),
    order_annotation={"state_name":"Возврат на ФБО","description":annotation["description"]},
    explicit_picking_pdf={"at":m.now(),"source":scope.get("source_pdf"),"counts":expected,"included_order_ids":scope["order_ids"],"priority":"User supplied physical picking list"})
  state.pop("error",None);state.pop("inflight",None);db.put(key,state)
  result.update(status="verified",quantity=sum(expected.values()),positions=len(expected),description=annotation["description"])
 except Exception as e:
  result.update(status="failed",error=str(e) if isinstance(e,m.Stop) else type(e).__name__)
 out["chains"].append(result);db.put(root+"result:v1",out)
out["status"]="complete" if all(x["status"]=="verified" for x in out["chains"]) else "requires_attention"
out["completed_at"]=m.now();db.put(root+"result:v1",out)
print(json.dumps({"status":out["status"],"verified":sum(x["status"]=="verified" for x in out["chains"])}))
if out["status"]!="complete":raise SystemExit(1)
