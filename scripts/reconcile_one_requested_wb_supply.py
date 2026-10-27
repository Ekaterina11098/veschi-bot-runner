"""Inspect or resume only one explicitly requested supply; secrets remain in runner."""
import os,sys,json
import fbs_document_chain as m
from fbs_wb_cabinets import ScopedCache
t=m.Transport();base=m.Cache(t);req=base.get("fbs_requested_supply:active:v1")
assert req.get("authorized") is True
sid=req["supply_id"];root="fbs_requested_supply:"+sid+":"
tokens={k:os.environ["WB_TOKEN_"+v] for k,v in {"china":"3","ip":"2","ooo":"1"}.items()}
if sys.argv[1]=="inspect":
 matches=[];errors=[]
 for cabinet in ("china","ip","ooo"):
  os.environ["WB_TOKEN_3"]=tokens[cabinet]
  try:
   supply=t.request(m.WB,"api/v3/supplies/"+sid)
   if supply.get("id")==sid:matches.append({"cabinet":cabinet,"supply":supply})
  except m.Stop as e:
   if not str(e).startswith("HTTP_404 "):errors.append({"cabinet":cabinet,"error":str(e)})
 out={"at":m.now(),"matches":matches,"probe_errors":errors}
 if len(matches)==1:
  item=matches[0];cabinet=item["cabinet"];c=base.get("fbs_document_chain:"+cabinet+":config:v1");w=m.Worker(t,base,c)
  out["state"]=base.get("fbs_document_chain:"+cabinet+":supply:v1:"+sid)
  out["existing_orders"]=w.ms_rows("entity/customerorder",{"filter":"name="+sid})
  out["status"]="ready" if item["supply"].get("done") and item["supply"].get("closedAt") else "waiting_delivery"
 else:out["status"]="not_found_or_ambiguous"
 base.put(root+"inspection:v1",out);print(json.dumps({"status":out["status"],"matched":len(matches)}))
elif sys.argv[1]=="resume":
 inspected=base.get(root+"inspection:v1");assert inspected["status"]=="ready" and len(inspected["matches"])==1
 item=inspected["matches"][0];cabinet=item["cabinet"];os.environ["WB_TOKEN_3"]=tokens[cabinet]
 m.CONFIG="fbs_document_chain:"+cabinet+":config:v1";m.STATE="fbs_document_chain:"+cabinet+":state:v1";m.PREFIX="fbs_document_chain:"+cabinet+":supply:v1:"
 db=ScopedCache(t,cabinet);c=db.get(m.CONFIG);assert c.get("writes_enabled") and c.get("status")=="active" and c.get("scope_confirmed")
 key=m.PREFIX+sid;state=db.get(key);w=m.Worker(t,db,c)
 state=state or {"supply":item["supply"],"status":"discovered","discovered_at":m.now(),"explicitly_requested":True}
 try:
  if state.get("status")!="complete":w.process(state)
  docs=[]
  for typ in m.TYPES:
   ref=state["documents"][typ];path="entity/"+typ+"/"+ref["id"]
   d=t.request(m.MS,path,params={"expand":"state,store,organization,agent"})
   ps=w.ms_rows(path+"/positions")
   payload=dict(c["templates"][typ],positions=state["positions"],description=state["order_annotation"]["description"])
   if typ=="demand":payload["customerOrder"]=state["documents"]["customerorder"]
   if typ=="salesreturn":payload["demand"]=state["documents"]["demand"]
   w.verify(typ,d,payload)
   docs.append({"type":typ,"id":d["id"],"name":d["name"],"quantity":sum(p["quantity"] for p in ps),"positions":len(ps),"posted":d.get("applicable"),"sum":d["sum"],"comment":d.get("description"),"store":d.get("store",{}).get("name"),"organization":d.get("organization",{}).get("name"),"agent":d.get("agent",{}).get("name"),"state":d.get("state",{}).get("name")})
  base.put(root+"result:v1",{"status":"verified","at":m.now(),"cabinet":cabinet,"supply":state["supply"],"documents":docs,"scope":db.get("fbs_document_chain:china:picking_scope:v1:"+sid)})
  print("Requested supply chain verified.")
 except Exception as e:
  state["error"]=str(e) if isinstance(e,m.Stop) else type(e).__name__;state["last_error_at"]=m.now();db.put(key,state)
  base.put(root+"result:v1",{"status":"failed","at":m.now(),"error":state["error"],"cabinet":cabinet})
  raise
else:raise m.Stop("Unsupported mode")
