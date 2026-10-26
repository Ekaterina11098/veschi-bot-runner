"""Read-only diagnosis of same-article WB picking-list colors."""
import datetime as dt,json,os,urllib.request,urllib.error,gzip
import fbs_document_chain as m
os.environ["WB_TOKEN_3"]=os.environ["WB_TOKEN_1"]
t=m.Transport();db=m.Cache(t)
out={"at":m.now(),"status":"reading","orders":[]}
wanted={5906318744,5900513083,5899579370}
cursor=0;seen=set()
begin=int(dt.datetime(2026,9,27,tzinfo=dt.timezone.utc).timestamp())
end=int(dt.datetime(2026,10,27,tzinfo=dt.timezone.utc).timestamp())
for page_no in range(40):
 response=t.request(m.WB,"api/v3/orders",params={"limit":1000,"next":cursor,"dateFrom":begin,"dateTo":end})
 batch=response.get("orders",[])
 for order in batch:
  if order.get("id") in wanted:out["orders"].append(order)
 if wanted.issubset({x["id"] for x in out["orders"]}):break
 nxt=response.get("next")
 if not batch or not nxt or nxt in seen:break
 seen.add(nxt);cursor=nxt
out["missing_order_ids"]=sorted(wanted-{x["id"] for x in out["orders"]})
db.put("wb:ip:article55:color_diagnosis:20261026",out)
# This exact POST endpoint lists cards and does not modify them.
url="https://content-api.wildberries.ru/content/v2/get/cards/list"
body={"settings":{"cursor":{"limit":100},"filter":{"withPhoto":-1,"textSearch":"55-NoelBag-green"}}}
req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={"Authorization":os.environ["WB_TOKEN_3"],"Content-Type":"application/json","Accept-Encoding":"gzip"},method="POST")
try:
 with urllib.request.urlopen(req,timeout=45) as r:
  raw=r.read()
  if r.headers.get("Content-Encoding")=="gzip":raw=gzip.decompress(raw)
  data=json.loads(raw)
 out["cards"]=[c for c in data.get("cards",[]) if (c.get("vendorCode") or "").strip().casefold()=="55-noelbag-green"]
except urllib.error.HTTPError as e:out["cards_error"]="HTTP_"+str(e.code)
except Exception:out["cards_error"]="transport_error"
out["status"]="verified";db.put("wb:ip:article55:color_diagnosis:20261026",out)
print(json.dumps({"status":"verified","orders":len(out["orders"]),"cards":len(out.get("cards",[]))}))
