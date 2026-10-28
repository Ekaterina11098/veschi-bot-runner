"""Read the requested live WB seller stock; never update stock."""
import os,json,urllib.request,urllib.error
import fbs_document_chain as m
t=m.Transport();db=m.Cache(t)
q=db.get("returns_stock_check:request:v1")
def wb(path,method="GET",body=None):
 assert path=="/api/v3/warehouses" and method=="GET" or path=="/api/v3/stocks/"+str(q["warehouse_id"]) and method=="POST"
 req=urllib.request.Request("https://marketplace-api.wildberries.ru"+path,data=None if body is None else json.dumps(body).encode(),headers={"Authorization":os.environ["WB_TOKEN_3"],"Content-Type":"application/json"},method=method)
 try:
  with urllib.request.urlopen(req,timeout=60) as r:return json.load(r)
 except urllib.error.HTTPError as e:raise m.Stop("WB read HTTP_"+str(e.code)) from None
warehouses=wb("/api/v3/warehouses")
assert len([x for x in warehouses if x["id"]==q["warehouse_id"] and x["name"]==q["warehouse_name"] and not x.get("isDeleting")])==1
data=wb("/api/v3/stocks/"+str(q["warehouse_id"]),"POST",{"chrtIds":[q["chrtId"]]})
rows=[x for x in data["stocks"] if x["chrtId"]==q["chrtId"]]
assert len(rows)==1 and type(rows[0]["amount"]) is int
db.put("returns_stock_check:result:v1",{"status":"verified","article":q["article"],"warehouse":q["warehouse_name"],"warehouse_id":q["warehouse_id"],"amount":rows[0]["amount"],"observed_at":m.now(),"stock_writes":0})
print(json.dumps({"status":"verified","stock_writes":0}))
