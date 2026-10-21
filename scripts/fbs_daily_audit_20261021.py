"""Read-only marketplace/MoySklad reconciliation for 2026-10-21 (Moscow)."""
import collections,json,os
import fbs_document_chain as m
from fbs_wb_cabinets import ScopedCache
import fbs_ozon_chain as oz
DAY="2026-10-21"
KEY="fbs_document_chain:daily_audit:v1:"+DAY
class ReadOnly(m.Transport):
 def request(self,base,path,method="GET",body=None,params=None):
  if base==m.MS and method!="GET":raise m.Stop("Audit prohibits document writes")
  return super().request(base,path,method,body,params)
t=ReadOnly();db=m.Cache(t)
report={"at":m.now(),"day_moscow":DAY,"status":"running","cabinets":{},"errors":[]}
tokens={k:os.environ["WB_TOKEN_"+v] for k,v in {"china":"3","ip":"2","ooo":"1"}.items()}
def today(value):
 return bool(value) and m.stamp(value).astimezone(m.dt.timezone(m.dt.timedelta(hours=3))).date().isoformat()==DAY
def signature(rows):
 out=collections.Counter()
 for p in rows:out[m.href(p["assortment"])]+=p["quantity"]
 return out
def check(w,cab,state,expected_positions,comment,order_name):
 if not state or state.get("status")!="complete":raise m.Stop("Missing or incomplete chain")
 links=state["documents"];result={"source":state["supply"]["id"],"quantity":sum(p["quantity"] for p in expected_positions),"documents":{},"comment":comment}
 if signature(state["positions"])!=signature(expected_positions):raise m.Stop("Marketplace picking scope differs from frozen chain")
 for typ in m.TYPES:
  ident=links[typ]["id"];doc=t.request(m.MS,"entity/"+typ+"/"+ident)
  payload=dict(w.c["templates"][typ],positions=expected_positions,description=comment)
  if typ=="demand":payload["customerOrder"]=links["customerorder"]
  if typ=="salesreturn":payload["demand"]=links["demand"]
  w.verify(typ,doc,payload)
  ext=w.c.get("document_prefix","fbs-china")+":"+state["supply"]["id"]+":"+typ
  matches=w.ms_rows("entity/"+typ,{"filter":"externalCode="+ext})
  if len(matches)!=1 or matches[0]["id"]!=ident:raise m.Stop("Duplicate/missing external-code document")
  if typ=="customerorder":
   if doc.get("name")!=order_name:raise m.Stop("Order name mismatch")
   status=t.request(m.MS,"entity/customerorder/metadata")
   states=[s for s in status["states"] if s.get("name")=="Возврат на ФБО"]
   if len(states)!=1 or m.href(doc.get("state",{}))!=m.href(states[0]):raise m.Stop("Order completion status mismatch")
   named=w.ms_rows("entity/customerorder",{"filter":"name="+order_name})
   duplicates=[d for d in named if d["id"]!=ident and (cab!="ozon" or d.get("description")==comment)]
  else:
   parent="customerOrder" if typ=="demand" else "demand"
   parenttype="customerorder" if typ=="demand" else "demand"
   parentid=links[parenttype]["id"]
   duplicates=[d for d in w.ms_rows("entity/"+typ,{"filter":parent+"="+m.MS+"entity/"+parenttype+"/"+parentid}) if d["id"]!=ident]
  if duplicates:raise m.Stop("Additional document for same source/link")
  result["documents"][typ]={"id":ident,"name":doc["name"],"posted":doc["applicable"],"sum":doc["sum"]}
 return result
for cab in ("china","ip","ooo"):
 block={"shipped":[],"waiting":[],"verified":[],"errors":[]};report["cabinets"][cab]=block
 try:
  os.environ["WB_TOKEN_3"]=tokens[cab]
  c=db.get("fbs_document_chain:"+cab+":config:v1");w=m.Worker(t,ScopedCache(t,cab),c)
  supplies=w.supplies()
  for s in supplies:
   if s.get("done") and today(s.get("closedAt")):
    block["shipped"].append(s["id"])
    try:
     state=db.get("fbs_document_chain:"+cab+":supply:v1:"+s["id"])
     positions,ids=w.positions(s)
     ann=w.order_annotation(s)
     block["verified"].append(check(w,cab,state,positions,ann["description"],s["id"]))
    except Exception as exc:block["errors"].append({"source":s["id"],"error":str(exc) if isinstance(exc,m.Stop) else type(exc).__name__})
 except Exception as exc:block["errors"].append({"error":str(exc) if isinstance(exc,m.Stop) else type(exc).__name__})
 db.put(KEY,report)
block={"shipped":[],"waiting":[],"verified":[],"errors":[]};report["cabinets"]["ozon"]=block
try:
 c=db.get("fbs_document_chain:ozon:config:v1")
 for act in oz.acts():
  if act.get("departure_date")!=DAY:continue
  sid="OZON-ACT-"+str(act["id"])
  try:
   scope=oz.snapshot(act)
   if not scope["ready"]:
    block["waiting"].append({"source":sid,"postings":scope["statuses"],"quantity":sum(scope["counts"].values())});continue
   block["shipped"].append(sid)
   state=db.get("fbs_document_chain:ozon:supply:v1:"+sid)
   w=oz.OzonWorker(t,db,c,act,scope);positions,ids=w.positions(oz.virtual_supply(act,scope))
   block["verified"].append(check(w,"ozon",state,positions,w.comment,w.order_name))
  except Exception as exc:block["errors"].append({"source":sid,"error":str(exc) if isinstance(exc,m.Stop) else type(exc).__name__})
except Exception as exc:block["errors"].append({"error":str(exc) if isinstance(exc,m.Stop) else type(exc).__name__})
report["errors"]=[{"cabinet":cab,**e} for cab,b in report["cabinets"].items() for e in b["errors"]]
report.update(status="verified" if not report["errors"] else "issues_found",completed_at=m.now())
db.put(KEY,report)
print(json.dumps({"status":report["status"],"verified_chains":sum(len(b["verified"]) for b in report["cabinets"].values()),"errors":len(report["errors"])}))
