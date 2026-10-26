"""Resume only the explicitly requested prepared supply through the existing verified chain."""
import json,time
import fbs_document_chain as m
class RetryReads(m.Transport):
 def request(self,base,path,method="GET",body=None,params=None):
  for n in range(3):
   try:return super().request(base,path,method,body,params)
   except m.Stop as e:
    if method!="GET" or not any(str(e).startswith("HTTP_"+str(x)) for x in (429,500,502,503,504)) or n==2:raise
    time.sleep(2*(n+1))
t=RetryReads();db=m.Cache(t);c=db.get(m.CONFIG)
assert c["status"]=="active" and c.get("writes_enabled") and c.get("scope_confirmed") is True
sid=db.get("fbs_document_chain:china:document_audit_request:v1")["supply_id"]
key=m.PREFIX+sid;state=db.get(key);assert state and state["supply"]["id"]==sid
w=m.Worker(t,db,c)
try:
 if state.get("status")!="complete":
  if not state.get("documents") and not state.get("inflight"):
   state["positions"],state["order_ids"]=w.positions(state["supply"])
   db.put(key,state)
  w.process(state)
 out={"status":"complete","at":m.now(),"supply_id":sid,"documents":state["documents"],"quantity":sum(p["quantity"] for p in state["positions"]),"positions":len(state["positions"]),"annotation":state.get("order_annotation")}
 db.put("fbs_document_chain:china:manual_resume:v1:"+sid,out)
 print(json.dumps({"status":"complete","document_count":len(out["documents"]),"quantity":out["quantity"]}))
except Exception as e:
 state["error"]=str(e) if isinstance(e,m.Stop) else type(e).__name__;state["last_error_at"]=m.now();db.put(key,state)
 raise
