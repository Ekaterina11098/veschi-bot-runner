import json,os,datetime as dt,urllib.request,gzip
from fbs_document_chain import *
t=Transport();db=Cache(t);sid="WB-GI-296250890"
state=db.get(PREFIX+sid)
report={"at":now(),"supply_id":sid,"journal_order_count":len(state["order_ids"]),"errors":[]}
try:
 report["supply"]=t.request(WB,"api/v3/supplies/"+sid)
 ids=t.request(WB,"api/marketplace/v3/supplies/"+sid+"/order-ids")["orderIds"]
 report["current_order_count"]=len(ids);report["added_ids"]=sorted(set(ids)-set(state["order_ids"]));report["removed_ids"]=sorted(set(state["order_ids"])-set(ids))
 req=urllib.request.Request(WB+"api/v3/orders/status",method="POST",headers={"Authorization":os.environ["WB_TOKEN_3"],"Content-Type":"application/json","Accept-Encoding":"gzip"},data=json.dumps({"orders":sorted(set(ids)|set(state["order_ids"]))}).encode())
 with urllib.request.urlopen(req,timeout=45) as r:
  raw=r.read()
  if r.headers.get("Content-Encoding")=="gzip":raw=gzip.decompress(raw)
  statuses=json.loads(raw)
 report["statuses"]=statuses
 end=dt.datetime.now(dt.timezone.utc);begin=end-dt.timedelta(days=30)+dt.timedelta(seconds=1)
 orders={};cursor=0;seen=set();wanted=set(ids)|set(state["order_ids"])
 while True:
  if cursor in seen:raise Stop("Pagination loop")
  seen.add(cursor)
  page=t.request(WB,"api/v3/orders",params={"limit":1000,"next":cursor,"dateFrom":int(begin.timestamp()),"dateTo":int(end.timestamp())})
  for row in page["orders"]:
   if row["id"] in wanted:orders[str(row["id"])]={k:row.get(k) for k in ["id","article","createdAt","supplyId","nmId","chrtId"]}
  if len(orders)==len(wanted) or not page["orders"] or not page["next"]:break
  cursor=page["next"]
 report["orders"]=orders
 report["found_orders"]=len(orders)
 report["non_complete"]=[dict(s,order=orders.get(str(s["id"]))) for s in statuses.get("orders",[]) if s.get("supplierStatus")!="complete" or s.get("wbStatus") in ("canceled","canceled_by_client","defect")]
except Exception as e:report["errors"].append(str(e) if isinstance(e,Stop) else type(e).__name__)
db.put("fbs_document_chain:china:quantity_audit:v1",report)
print(json.dumps({"saved":True,"errors":report["errors"],"document_writes":0}))
