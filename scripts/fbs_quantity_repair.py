import json,collections
from fbs_document_chain import *
SID="WB-GI-296250890";ARTICLE="534-NoelBag-emerald";CANCELLED=6071589005
KEY="fbs_document_chain:china:quantity_repair:v1"
t=Transport();db=Cache(t);c=db.get(CONFIG);w=Worker(t,db,c)
proof={"at":now(),"supply_id":SID,"excluded_order_id":CANCELLED,"article":ARTICLE,"target_quantity":220,"status":"preflight","steps":[]}
try:
 state=db.get(PREFIX+SID)
 products=w.ms_rows("entity/product",{"filter":"article="+ARTICLE})
 products=[p for p in products if p.get("article","").casefold()==ARTICLE.casefold() and not p.get("archived")]
 if len(products)!=1:raise Stop("Repair product ambiguous")
 target=href(products[0])
 status=t.request(WB,"api/v3/orders/status",method="POST",body={"orders":[CANCELLED]})["orders"]
 if len(status)!=1 or status[0]["id"]!=CANCELLED or status[0].get("wbStatus")!="canceled_by_client":raise Stop("Exact cancellation not verified")
 original=state["positions"]
 desired=json.loads(json.dumps(original))
 matched=[p for p in desired if href(p["assortment"])==target]
 if sum(p["quantity"] for p in original)!=221 and state.get("quantity_corrected_to")!=220:raise Stop("Unexpected journal quantity")
 if state.get("quantity_corrected_to")!=220:
  if len(matched)!=1 or matched[0]["quantity"]<1:raise Stop("Expected canceled product not in journal")
  matched[0]["quantity"]-=1
  desired=[p for p in desired if p["quantity"]>0]
 if sum(p["quantity"] for p in desired)!=220:raise Stop("Repair target not 220")
 def quantities(rows):
  result=collections.Counter()
  for p in rows:
   if p["price"]!=0:raise Stop("Nonzero price")
   result[href(p["assortment"])]+=p["quantity"]
  return result
 snapshots={}
 for typ in TYPES:
  ident=state["documents"][typ]["id"]
  rows=w.ms_rows("entity/"+typ+"/"+ident+"/positions")
  if quantities(rows) not in (quantities(original),quantities(desired)):raise Stop("Current document differs from known original and target")
  snapshots[typ]=rows
 proof["before"]={typ:sum(p["quantity"] for p in rows) for typ,rows in snapshots.items()}
 proof["original_positions"]=original
 db.put(KEY,proof)
 # Reduce the return first so it cannot exceed its source demand.
 for typ in ("salesreturn","demand","customerorder"):
  ident=state["documents"][typ]["id"];rows=snapshots[typ]
  if quantities(rows)!=quantities(desired):
   candidates=[p for p in rows if href(p["assortment"])==target]
   if len(candidates)!=1:raise Stop("Expected unique document position missing")
   p=candidates[0];path="entity/"+typ+"/"+ident+"/positions/"+p["id"]
   proof["inflight"]=typ;db.put(KEY,proof)
   if p["quantity"]==1:t.request(MS,path,"DELETE")
   else:t.request(MS,path,"PUT",{"quantity":p["quantity"]-1})
  doc=t.request(MS,"entity/"+typ+"/"+ident)
  payload=dict(c["templates"][typ],positions=desired,description=state["order_annotation"]["description"])
  w.verify(typ,doc,payload)
  proof.pop("inflight",None);proof["steps"].append({"type":typ,"quantity":220,"posted":doc["applicable"]})
  db.put(KEY,proof)
 state["positions"]=desired;state["quantity_corrected_to"]=220
 state["excluded_order_ids"]=[CANCELLED];state["quantity_correction_at"]=now();state["status"]="complete"
 db.put(PREFIX+SID,state)
 proof.update(status="verified",completed_at=now());db.put(KEY,proof)
 print(json.dumps({"status":"verified","quantity":220,"documents":3}))
except Exception as e:
 proof["error"]=str(e) if isinstance(e,Stop) else type(e).__name__;proof["status"]="failed";db.put(KEY,proof)
 print(json.dumps({"status":"failed","error":proof["error"]}))
 raise SystemExit(1)
