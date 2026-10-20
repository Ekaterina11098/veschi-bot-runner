"""Rename the first verified Ozon order, preserving all other document fields."""
import json
import fbs_document_chain as m
from fbs_comment_audit import audit_chain

t=m.Transport();db=m.Cache(t)
key="fbs_document_chain:ozon:supply:v1:OZON-ACT-124091131"
proof_key="fbs_document_chain:ozon:name_repair:v1"
state=db.get(key)
if not state or state.get("status")!="complete":raise m.Stop("Expected completed Ozon act missing")
audit_chain(t,db,"ozon",state)
ident=state["documents"]["customerorder"]["id"]
if ident!="694c03c6-cc94-11f1-0a80-1e38003c6c08":raise m.Stop("Unexpected order identity")
path="entity/customerorder/"+ident
before=t.request(m.MS,path)
expected="201026 Озон"
if before.get("name") not in ("201026",expected):raise m.Stop("Order was renamed manually; reconcile")
if before["name"]!=expected:t.request(m.MS,path,"PUT",{"name":expected})
after=t.request(m.MS,path)
if after.get("name")!=expected:raise m.Stop("Order name readback mismatch")
for field in ("description","applicable","sum","organization","agent","store","state","externalCode"):
 if before.get(field)!=after.get(field):raise m.Stop("Unexpected field change: "+field)
audit_chain(t,db,"ozon",state)
state["documents"]["customerorder"]["name"]=expected
db.put(key,state)
db.put(proof_key,{"status":"verified","at":m.now(),"act_id":124091131,"order_id":ident,"name":expected,"other_fields_verified":True})
print(json.dumps({"status":"verified","order_name":expected},ensure_ascii=False))
