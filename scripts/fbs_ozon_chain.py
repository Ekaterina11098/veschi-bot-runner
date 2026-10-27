"""One Ozon act -> one zero-price posted chain, only after delivery transition."""
import collections,datetime as dt,json,sys
import fbs_document_chain as m
from fbs_ozon_api import ozon
m.CONFIG="fbs_document_chain:ozon:config:v1"
m.STATE="fbs_document_chain:ozon:state:v1"
m.PREFIX="fbs_document_chain:ozon:supply:v1:"
CONFIG,STATE,PREFIX=m.CONFIG,m.STATE,m.PREFIX
READY={"delivering","delivered"}
CANCELLED={"cancelled","canceled"}

def totals(products):
 out=collections.Counter()
 for p in products:
  article=p.get("offer_id");quantity=p.get("quantity")
  if not isinstance(article,str) or not article.strip() or not isinstance(quantity,int) or quantity<=0:
   raise m.Stop("Ozon article/quantity invalid")
  out[article.strip().casefold()]+=quantity
 return out

def acts():
 end=dt.datetime.now(dt.timezone.utc).date()
 response=ozon("/v2/posting/fbs/act/list",{"limit":50,"filter":{"date_from":str(end-dt.timedelta(days=7)),"date_to":str(end)}})
 rows=response.get("result")
 if not isinstance(rows,list) or len(rows)>=50:raise m.Stop("Ozon act-list scope incomplete")
 if len({a["id"] for a in rows})!=len(rows):raise m.Stop("Duplicate Ozon act IDs")
 return rows

def snapshot(act):
 if act.get("is_partial") or act.get("has_postings_for_next_carriage"):raise m.Stop("Partial/split Ozon act needs reconciliation")
 rows=ozon("/v2/posting/fbs/act/get-postings",{"id":act["id"]}).get("result")
 if not isinstance(rows,list) or not rows:raise m.Stop("Ozon act has no complete posting list")
 numbers=[r.get("posting_number") for r in rows]
 if any(not isinstance(n,str) or not n for n in numbers) or len(set(numbers))!=len(numbers):raise m.Stop("Ozon act posting IDs missing/duplicated")
 included=[];excluded=[];states={};dates=[];counts=collections.Counter()
 for row in rows:
  if row.get("status")!="success":raise m.Stop("Ozon act contains unsuccessfully formed posting")
  number=row["posting_number"]
  post=ozon("/v3/posting/fbs/get",{"posting_number":number,"with":{"analytics_data":False,"financial_data":False}}).get("result",{})
  if post.get("posting_number")!=number:raise m.Stop("Ozon posting readback mismatch")
  states[number]=post.get("status")
  after_ship=post.get("cancellation",{}).get("cancelled_after_ship") is True
  if post.get("status") in CANCELLED and not after_ship:
   excluded.append(number);continue
  if totals(post.get("products",[]))!=totals(row.get("products",[])):raise m.Stop("Ozon act/posting product composition differs")
  included.append(number);counts.update(totals(row["products"]))
  if post.get("delivering_date"):dates.append(post["delivering_date"])
  if after_ship:states[number]="delivering"
 return {"all_numbers":sorted(numbers),"included":sorted(included),"excluded":sorted(excluded),
         "counts":dict(counts),"statuses":states,
         "ready":bool(included) and all(states[n] in READY for n in included),
         "movement_at":max(dates) if dates else m.now()}

class OzonWorker(m.Worker):
 def __init__(self,t,db,c,act,scope):
  super().__init__(t,db,c);self.act=act;self.scope=scope
  self.comment=", ".join(scope["included"])
  self.order_name=dt.date.fromisoformat(act["departure_date"]).strftime("%d%m%y")+" Озон"
 def order_annotation(self,supply):
  metadata=self.t.request(m.MS,"entity/customerorder/metadata")
  states=[s for s in metadata.get("states",[]) if s.get("name")=="Возврат на ФБО"]
  if len(states)!=1:raise m.Stop("Required order state missing/ambiguous")
  return {"state":m.meta(states[0]),"description":self.comment}
 def positions(self,supply):
  index={}
  for p in self.ms_rows("entity/product",{"filter":"archived=false"}):
   if isinstance(p.get("article"),str) and not p.get("archived"):index.setdefault(p["article"].strip().casefold(),[]).append(p)
  positions=[]
  for article,quantity in sorted(self.scope["counts"].items()):
   products=index.get(article,[])
   if len(products)!=1 or products[0].get("variantsCount",0) or products[0].get("isSerialTrackable") or products[0].get("trackingType","NOT_TRACKED")!="NOT_TRACKED":
    raise m.Stop("Ozon article missing, ambiguous or requires marking: "+article)
   positions.append({"assortment":m.meta(products[0]),"quantity":quantity,"price":0,"discount":0,"vat":0,"vatEnabled":False})
  if not positions or len(positions)>1000:raise m.Stop("Ozon document position scope invalid")
  return positions,self.scope["all_numbers"]
 def validate_source(self,state):
  current=snapshot(self.act)
  if not current["ready"] or current["all_numbers"]!=state["order_ids"] or current["counts"]!=self.scope["counts"] or current["included"]!=self.scope["included"]:
   raise m.Stop("Ozon act status/composition changed")
 def ensure(self,typ,payload,state,key):
  if typ=="customerorder":
   payload=dict(payload,name=self.order_name)
   manual=self.ms_rows("entity/customerorder",{"filter":"name="+self.order_name})
   expected=self.c["document_prefix"]+":"+state["supply"]["id"]+":customerorder"
   if any(d.get("description")==self.comment and d.get("externalCode")!=expected for d in manual):
    raise m.Stop("Manual Ozon order already contains this act posting set")
   if any(d.get("externalCode")!=expected for d in manual):
    # Several acts may depart on one date; keep the date prefix while giving
    # later acts a stable unique number. Never combine unrelated act scopes.
    payload["name"]=self.order_name+" "+str(self.act["id"])
    collisions=self.ms_rows("entity/customerorder",{"filter":"name="+payload["name"]})
    if any(d.get("externalCode")!=expected for d in collisions):
     raise m.Stop("Ozon order number collision requires reconciliation")
  return super().ensure(typ,payload,state,key)

def virtual_supply(act,scope):
 return {"id":"OZON-ACT-"+str(act["id"]),"name":"Озон","closedAt":scope["movement_at"],"done":True,"createdAt":act["created_at"]}

def main(mode):
 t=m.Transport();db=m.Cache(t);c=db.get(CONFIG)
 if not c or c.get("cabinet")!="ozon":raise m.Stop("Ozon configuration missing")
 if mode=="run" and (not c.get("writes_enabled") or c.get("status")!="active"):
  print(json.dumps({"status":"paused","writes":0}));return
 baseline=db.get(STATE);start=m.now()
 if mode=="setup" and baseline:raise m.Stop("Ozon baseline exists; reset prohibited")
 if mode=="run" and not baseline:raise m.Stop("Ozon activation baseline missing")
 listed=acts()
 if mode=="setup":
  old=[];watched=[];preview=[]
  for act in listed:
   if act.get("status")=="closed":old.append(act["id"]);continue
   scope=snapshot(act)
   worker=OzonWorker(t,db,c,act,scope)
   if scope["included"]:
    positions,ids=worker.positions(virtual_supply(act,scope));worker.order_annotation(virtual_supply(act,scope))
    preview.append({"act_id":act["id"],"order_name":worker.order_name,"comment":worker.comment,"postings":len(scope["included"]),"quantity":sum(p["quantity"] for p in positions),"ready":scope["ready"]})
   if not scope["included"] or (scope["ready"] and m.stamp(scope["movement_at"])<m.stamp(start)):
    old.append(act["id"])
   else:
    state={"act":act,"supply":virtual_supply(act,scope),"status":"waiting_delivery","observed_scope":scope}
    db.put(PREFIX+state["supply"]["id"],state);watched.append(act["id"])
  db.put(STATE,{"activated_at":start,"baseline_delivering_act_ids":old,"watched_act_ids":watched})
  db.put("fbs_document_chain:ozon:preview:v1",{"at":m.now(),"result":preview,"writes":0})
  c["status"]="preview_verified";c["setup_verified_at"]=m.now();db.put(CONFIG,c)
  print(json.dumps({"status":"baseline_and_preview_verified","writes":0}));return
 if mode!="run":raise m.Stop("Unknown Ozon mode")
 old=set(baseline["baseline_delivering_act_ids"])
 pending={x["payload"]["act"]["id"]:x["payload"] for x in db.pending()}
 known={a["id"]:a for a in listed if a["id"] not in old}
 for ident,state in pending.items():known.setdefault(ident,state["act"])
 errors=[];completed=0
 for ident,act in known.items():
  key=PREFIX+"OZON-ACT-"+str(ident);state=db.get(key)
  if state and state.get("status")=="complete":continue
  if not state and m.stamp(act["created_at"])<=m.stamp(baseline["activated_at"]):continue
  try:
   scope=snapshot(act)
   state=state or {"act":act,"status":"waiting_delivery"}
   state["supply"]=virtual_supply(act,scope)
   if not scope["included"]:
    if state.get("documents") or state.get("inflight"):raise m.Stop("All postings canceled after chain began; reconcile existing documents")
    state.update(status="complete",skipped_all_cancelled=True);db.put(key,state);continue
   if not scope["ready"]:
    state["observed_scope"]=scope;db.put(key,state);continue
   worker=OzonWorker(t,db,c,act,scope)
   if "positions" in state and (state.get("picking_scope",{}).get("included")!=scope["included"] or state.get("picking_scope",{}).get("counts")!=scope["counts"]):
    raise m.Stop("Frozen Ozon act composition changed")
   state["picking_scope"]=scope;db.put(key,state)
   worker.process(state)
   completed+=1
  except Exception as exc:
   error=str(exc) if isinstance(exc,m.Stop) else type(exc).__name__
   if state:state["error"]=error;state["last_error_at"]=m.now();db.put(key,state)
   errors.append({"act_id":ident,"error":error})
 db.put("fbs_document_chain:ozon:last_run:v1",{"at":m.now(),"completed":completed,"errors":errors})
 if errors:raise m.Stop("Ozon act chains require attention; see private journal")
 print(json.dumps({"status":"done","completed":completed}))
if __name__=="__main__":
 try:main(sys.argv[1] if len(sys.argv)>1 else "run")
 except Exception as exc:
  print(json.dumps({"status":"failed","error":str(exc) if isinstance(exc,m.Stop) else type(exc).__name__}))
  sys.exit(1)
