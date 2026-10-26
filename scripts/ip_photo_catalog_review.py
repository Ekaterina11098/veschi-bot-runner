"""Read-only IP photo catalog for explicit copyright image comparison."""
import json,os,gzip,time,urllib.request
import fbs_document_chain as m
t=m.Transport();db=m.Cache(t);root="photo_rights_review:ip:20261026:"
cursor={"limit":100};count=0;page=0;seen=set()
proof={"status":"reading","at":m.now(),"cabinet":"ip","pages":[]}
while True:
 body={"settings":{"cursor":cursor,"filter":{"withPhoto":-1}}}
 req=urllib.request.Request("https://content-api.wildberries.ru/content/v2/get/cards/list",data=json.dumps(body).encode(),method="POST",headers={"Authorization":os.environ["WB_TOKEN_2"],"Content-Type":"application/json","Accept-Encoding":"gzip"})
 with urllib.request.urlopen(req,timeout=60) as r:
  raw=r.read()
  if r.headers.get("Content-Encoding")=="gzip":raw=gzip.decompress(raw)
  data=json.loads(raw)
 cards=[{k:c.get(k) for k in ("nmID","vendorCode","title","photos","createdAt","updatedAt","brand")} for c in data.get("cards",[])]
 for c in cards:assert c["nmID"] not in seen;seen.add(c["nmID"])
 db.put(root+"cards:"+str(page),cards);count+=len(cards)
 proof["pages"].append({"page":page,"count":len(cards)});proof["count"]=count
 db.put(root+"catalog:v1",proof)
 nxt=data.get("cursor",{})
 if len(cards)<100 or nxt.get("total",0)<100:break
 cursor={"limit":100,"updatedAt":nxt["updatedAt"],"nmID":nxt["nmID"]};page+=1
 assert page<100
 time.sleep(.7)
proof["status"]="complete";proof["completed_at"]=m.now();db.put(root+"catalog:v1",proof)
print(json.dumps({"status":"complete","cards":count}))
