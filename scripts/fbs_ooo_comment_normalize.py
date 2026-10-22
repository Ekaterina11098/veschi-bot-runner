import json
import fbs_document_chain as m
from fbs_comment_audit import audit_chain
t=m.Transport();db=m.Cache(t)
key="fbs_document_chain:ooo:supply:v1:WB-GI-296787917"
state=db.get(key);c=db.get("fbs_document_chain:ooo:config:v1")
if not state or state.get("status")!="complete":raise m.Stop("Expected completed chain missing")
expected=m.Worker(t,db,c).order_annotation(state["supply"])["description"]
if expected!="21 10 26  Киргизия МСК":raise m.Stop("Unexpected normalized comment")
before=state["order_annotation"]["description"]
if before not in (expected,"21 10 26  Киргизия К МСК"):raise m.Stop("Recorded comment changed unexpectedly")
state["order_annotation"]["description"]=expected
db.put(key,state)
proof=audit_chain(t,db,"ooo",state)
proof.update(status="verified",at=m.now(),comment=expected)
db.put("fbs_document_chain:ooo:comment_normalization:v1",proof)
c["order_annotation"].update(comment_format="DD MM YY  Киргизия <группа без префикса К или Киргизия>",example=expected)
db.put("fbs_document_chain:ooo:config:v1",c)
print(json.dumps({"status":"verified","documents":3},ensure_ascii=False))
