import os,json,urllib.request,datetime as d
from fbs_document_chain import *
t=Transport();db=Cache(t);c=db.get(CONFIG);w=Worker(t,db,c)
report={"at":now(),"credentials":{k:bool(os.getenv(k)) for k in ["WB_TOKEN_1","WB_TOKEN_2","OZON_CLIENT_ID","OZON_API_KEY"]},"errors":[]}
try:
 report["buyers"]=[]
 for ident in ["4cc3ffa2-fd7c-11ee-0a80-0b56002b7934","8d53524f-07ad-11ef-0a80-16a20045f991"]:
  p=t.request(MS,"entity/counterparty/"+ident);report["buyers"].append({"id":p["id"],"name":p["name"]})
 report["orders"]=t.request(MS,"entity/customerorder",params={"limit":30,"order":"moment,desc","expand":"agent,organization,store"})["rows"]
 report["returns"]=t.request(MS,"entity/salesreturn",params={"limit":30,"order":"moment,desc","expand":"agent,organization,store"})["rows"]
 report["wb"]={}
 for cabinet in ["1","2"]:
  os.environ["WB_TOKEN_3"]=os.environ["WB_TOKEN_"+cabinet]
  report["wb"][cabinet]=t.request(WB,"api/v3/supplies",params={"limit":1000,"next":0})
 if report["credentials"]["OZON_CLIENT_ID"] and report["credentials"]["OZON_API_KEY"]:
  end=d.datetime.now(d.timezone.utc);begin=end-d.timedelta(days=2)
  req=urllib.request.Request("https://api-seller.ozon.ru/v2/posting/fbs/act/list",method="POST",headers={"Client-Id":os.environ["OZON_CLIENT_ID"],"Api-Key":os.environ["OZON_API_KEY"],"Content-Type":"application/json"},data=json.dumps({"limit":100,"filter":{"date_from":begin.isoformat(),"date_to":end.isoformat()}}).encode())
  try:
   with urllib.request.urlopen(req,timeout=40) as response:report["ozon_acts"]=json.load(response)
  except urllib.error.HTTPError as e:report["errors"].append("ozon_acts_HTTP_"+str(e.code))
except Exception as e:report["errors"].append(str(e) if isinstance(e,Stop) else type(e).__name__)
db.put("fbs_document_chain:expansion:inventory:v1",report)
print(json.dumps({"saved":True,"errors":report["errors"],"document_writes":0}))
