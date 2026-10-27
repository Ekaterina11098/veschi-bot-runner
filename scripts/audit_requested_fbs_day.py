"""Read every shipment in a privately requested Moscow day, independently of ledger completeness."""
import os,json,datetime as dt,collections,time
import fbs_document_chain as m
from fbs_wb_cabinets import ScopedCache
class ReviewTransport(m.Transport):
 def request(self,base,path,method="GET",body=None,params=None):
  semantic_read=base==m.WB and method=="POST" and path=="api/v3/orders/status"
  for attempt in range(3 if semantic_read else 1):
   try:return super().request(base,path,method,body,params)
   except m.Stop as e:
    transient=str(e)=="API transport outcome uncertain" or any(str(e).startswith("HTTP_"+str(n)) for n in (429,500,502,503,504))
    if not semantic_read or not transient or attempt==2:
     label="MS" if base==m.MS else "WB" if base==m.WB else "private_cache"
     raise m.Stop(str(e)+" ["+label+" "+method+" "+path+"]") from None
    time.sleep(2*(attempt+1))
def bounded_rows(self,path,params=None):
 rows=[];offset=0
 while True:
  data=self.t.request(m.MS,path,params={**(params or {}),"limit":100,"offset":offset})
  batch=data.get("rows")
  if not isinstance(batch,list) or not isinstance(data.get("meta",{}).get("size"),int):raise m.Stop("Incomplete collection")
  rows+=batch
  if len(rows)==data["meta"]["size"]:return rows
  if not batch or len(rows)>20000:raise m.Stop("Incomplete collection pagination")
  offset+=len(batch)
m.Worker.ms_rows=bounded_rows
t=ReviewTransport();db=m.Cache(t);reader=m.Worker(t,db,{})
root=os.environ["DAY_REVIEW_ROOT"];req=db.get(root+"request:v1")
target=os.environ.get("TARGET_CABINET");audit_key=root+"audit:"+target+":v1" if target else root+"audit:v1"
day=dt.date.fromisoformat(req["date"]);tz=dt.timezone(dt.timedelta(hours=3))
begin=dt.datetime.combine(day,dt.time.min,tzinfo=tz);end=begin+dt.timedelta(days=1)
def within(value):return bool(value) and begin<=m.stamp(value)<end
tokens={k:os.environ["WB_TOKEN_"+v] for k,v in {"china":"3","ip":"2","ooo":"1"}.items()}
report={"at":m.now(),"date":str(day),"status":"running","chains":[],"waiting":[],"errors":[],"source":"live API, not PDF"}
recent={}
for typ in m.TYPES:recent[typ]=reader.ms_rows("entity/"+typ,{"filter":"moment>="+begin.strftime("%Y-%m-%d %H:%M:%S")+";moment<"+end.strftime("%Y-%m-%d %H:%M:%S")})
def counts(ps):
 c=collections.Counter()
 for p in ps:c[(p["assortment"].get("article") or "").strip().casefold()]+=p["quantity"]
 return dict(c)
def inspect(cabinet,supply,expected,scope,worker,annotation,act=None):
 sid=supply["id"];config=worker.c
 state=db.get("fbs_document_chain:"+cabinet+":supply:v1:"+sid)
 result={"cabinet":cabinet,"supply":supply,"scope":scope,"expected":expected,"expected_quantity":sum(expected.values()),"annotation":{"description":annotation["description"],"state":annotation["state"]},"act":act,"state_status":(state or {}).get("status"),"documents":[],"issues":[]}
 prefix=config.get("document_prefix","fbs-china");refs={}
 for typ in m.TYPES:
  candidates={}
  for d in worker.ms_rows("entity/"+typ,{"filter":"moment>="+begin.strftime("%Y-%m-%d %H:%M:%S")+";externalCode="+prefix+":"+sid+":"+typ}):candidates[d["id"]]=d
  if state and typ in state.get("documents",{}):
   uid=state["documents"][typ]["id"];candidates[uid]=t.request(m.MS,"entity/"+typ+"/"+uid)
  if typ=="customerorder":
   if cabinet!="ozon":
    for d in worker.ms_rows("entity/customerorder",{"filter":"moment>="+begin.strftime("%Y-%m-%d %H:%M:%S")+";name="+sid}):candidates[d["id"]]=d
   else:
    for d in recent[typ]:
     if any(n in (d.get("description") or "") for n in scope["included"]):candidates[d["id"]]=d
  else:
   link="customerOrder" if typ=="demand" else "demand";basis="customerorder" if typ=="demand" else "demand"
   for d in recent[typ]:
    if m.href(d.get(link,{})) in refs.get(basis,[]):candidates[d["id"]]=d
  live=[d for d in candidates.values() if not d.get("deleted")]
  refs[typ]=[m.href(d) for d in live]
  if len(live)!=1:result["issues"].append({"type":typ,"issue":"missing" if not live else "duplicate","count":len(live)})
  for d in candidates.values():
   ps=worker.ms_rows("entity/"+typ+"/"+d["id"]+"/positions",{"expand":"assortment"})
   actual=counts(ps)
   checks={"active":not bool(d.get("deleted")),"posted":d.get("applicable") is True,"zero":d["sum"]==0 and all(p["price"]==0 for p in ps),"counts":actual==expected,"comment":d.get("description")==annotation["description"],"common":all(m.href(d.get(k,{}))==m.href(config["templates"][typ][k]) for k in ("organization","agent","store"))}
   if typ=="customerorder":checks["state"]=m.href(d.get("state",{}))==m.href(annotation["state"])
   if typ=="demand":checks["basis"]=m.href(d.get("customerOrder",{})) in refs.get("customerorder",[])
   if typ=="salesreturn":checks["basis"]=m.href(d.get("demand",{})) in refs.get("demand",[])
   rec={"type":typ,"id":d["id"],"name":d["name"],"checks":checks,"counts":actual,"quantity":sum(actual.values()),"missing":dict(collections.Counter(expected)-collections.Counter(actual)),"extra":dict(collections.Counter(actual)-collections.Counter(expected)),"comment":d.get("description"),"deleted":d.get("deleted"),"externalCode":d.get("externalCode")}
   result["documents"].append(rec)
   if not d.get("deleted"):
    for k,v in checks.items():
     if not v:result["issues"].append({"type":typ,"id":d["id"],"issue":k})
 result["status"]="verified" if not result["issues"] else "requires_repair"
 report["chains"].append(result);db.put(audit_key,report)
for cabinet in ("china","ip","ooo"):
 if target and target!=cabinet:continue
 os.environ["WB_TOKEN_3"]=tokens[cabinet]
 scoped=ScopedCache(t,cabinet);config=scoped.get("fbs_document_chain:"+cabinet+":config:v1");worker=m.Worker(t,scoped,config)
 try:
  listed=worker.supplies()
  supplies=[s for s in listed if s.get("done") is True and within(s.get("closedAt"))]
  report["waiting"] += [{"cabinet":cabinet,"supply":s,"reason":"not_in_delivery"} for s in listed if not s.get("done") and within(s.get("createdAt"))]
  ids_by={s["id"]:t.request(m.WB,"api/marketplace/v3/supplies/"+s["id"]+"/order-ids")["orderIds"] for s in supplies}
  wanted={i for ids in ids_by.values() for i in ids}
  found={};cursor=0;visited=set();now=dt.datetime.now(dt.timezone.utc)
  while set(found)!=wanted:
   if cursor in visited:raise m.Stop("Order pagination repeated")
   visited.add(cursor)
   page=t.request(m.WB,"api/v3/orders",params={"limit":1000,"next":cursor,"dateFrom":int((now-dt.timedelta(days=30)+dt.timedelta(seconds=1)).timestamp()),"dateTo":int(now.timestamp())})
   rows=page.get("orders")
   if not isinstance(rows,list):raise m.Stop("Incomplete source orders")
   for order in rows:
    if order["id"] in wanted:found[order["id"]]=order
   if set(found)==wanted:break
   if not rows or not page.get("next"):raise m.Stop("Not all source IDs found")
   cursor=page["next"]
  statuses={}
  allids=sorted(wanted)
  for n in range(0,len(allids),100):
   for status in t.request(m.WB,"api/v3/orders/status","POST",{"orders":allids[n:n+100]})["orders"]:statuses[status["id"]]=status
  if set(statuses)!=wanted:raise m.Stop("Status scope incomplete")
  for supply in supplies:
   ids=ids_by[supply["id"]];included=[i for i in ids if not m.excluded_from_picking(statuses[i])]
   expected=dict(collections.Counter(found[i]["article"].strip().casefold() for i in included))
   scope={"all_numbers":sorted(ids),"included":sorted(included),"excluded":[{"id":i,"article":found[i]["article"],"status":statuses[i]} for i in ids if i not in included],"counts":expected,"raw_count":len(ids)}
   inspect(cabinet,supply,expected,scope,worker,worker.order_annotation(supply))
 except Exception as e:report["errors"].append({"cabinet":cabinet,"error":str(e) if isinstance(e,m.Stop) else type(e).__name__})
 db.put(audit_key,report)
if not target or target=="ozon":
 from fbs_ozon_chain import acts,snapshot,OzonWorker,virtual_supply
 try:
  config=db.get("fbs_document_chain:ozon:config:v1")
  for act in acts():
   if act.get("departure_date")!=str(day):continue
   scope=snapshot(act);supply=virtual_supply(act,scope)
   if not scope["ready"]:
    report["waiting"].append({"cabinet":"ozon","act":act,"scope":scope,"reason":"not_all_postings_in_delivery"});continue
   worker=OzonWorker(t,db,config,act,scope)
   inspect("ozon",supply,scope["counts"],scope,worker,worker.order_annotation(supply),act)
 except Exception as e:report["errors"].append({"cabinet":"ozon","error":str(e) if isinstance(e,m.Stop) else type(e).__name__})
report["status"]="audited" if not report["errors"] else "incomplete"
report["completed_at"]=m.now();db.put(audit_key,report)
print(json.dumps({"status":report["status"],"chains":len(report["chains"]),"issues":sum(len(c["issues"]) for c in report["chains"]),"source_errors":len(report["errors"])}))
if report["errors"]:raise SystemExit(1)
