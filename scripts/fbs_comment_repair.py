import json
from fbs_document_chain import *
SID="WB-GI-296254552";KEY="fbs_document_chain:china:comment_repair:v1"
t=Transport();db=Cache(t);c=db.get(CONFIG);w=Worker(t,db,c);state=db.get(PREFIX+SID)
proof={"supply_id":SID,"at":now(),"status":"preflight","steps":[]}
try:
 docs={};rows={}
 for typ in TYPES:
  ident=state["documents"][typ]["id"]
  docs[typ]=t.request(MS,"entity/"+typ+"/"+ident)
  rows[typ]=w.ms_rows("entity/"+typ+"/"+ident+"/positions")
 order=docs["customerorder"]
 comment=order.get("description","")
 if order.get("name")!=SID or " ".join(comment.split())!="20 10 26 Гонконг Зонты":raise Stop("Order comment/source does not match requested chain")
 if href(docs["demand"].get("customerOrder",{}))!=href(order):raise Stop("Demand order link differs")
 if href(docs["salesreturn"].get("demand",{}))!=href(docs["demand"]):raise Stop("Return demand link differs")
 proof["comment"]=comment
 proof["before"]={typ:{"description":docs[typ].get("description"),"quantity":sum(p["quantity"] for p in rows[typ]),"applicable":docs[typ].get("applicable")} for typ in TYPES}
 db.put(KEY,proof)
 for typ in TYPES:
  path="entity/"+typ+"/"+docs[typ]["id"]
  if docs[typ].get("description")!=comment:
   proof["inflight"]=typ;db.put(KEY,proof)
   t.request(MS,path,"PUT",{"description":comment})
  after=t.request(MS,path)
  expected={k:docs[typ][k] for k in ["organization","agent","store","customerOrder","demand"] if k in docs[typ]}
  expected.update(positions=rows[typ],description=comment)
  w.verify(typ,after,expected)
  if after.get("applicable")!=docs[typ].get("applicable"):raise Stop("Posted state changed")
  proof.pop("inflight",None)
  proof["steps"].append({"type":typ,"name":after["name"],"description":after["description"],"quantity":sum(p["quantity"] for p in rows[typ]),"posted":after.get("applicable")})
  db.put(KEY,proof)
 state["order_annotation"]={"state_name":"Возврат на ФБО","description":comment}
 state["comment_correction_at"]=now();db.put(PREFIX+SID,state)
 proof.update(status="verified",completed_at=now());db.put(KEY,proof)
 print(json.dumps({"status":"verified","documents":3,"quantities_unchanged":True}))
except Exception as e:
 proof.update(status="failed",error=str(e) if isinstance(e,Stop) else type(e).__name__);db.put(KEY,proof)
 print(json.dumps({"status":"failed","error":proof["error"]}));raise SystemExit(1)
