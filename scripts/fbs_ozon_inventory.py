import os,json,urllib.request,datetime as d
from fbs_document_chain import *
t=Transport();db=Cache(t)
end=d.datetime.now(d.timezone.utc);begin=end-d.timedelta(days=7)
req=urllib.request.Request(os.environ["SUPABASE_URL"].rstrip("/")+"/functions/v1/fbs-ozon-read",method="POST",headers={"x-fbs-backend-key":os.environ["SUPABASE_SECRET_KEY"],"Content-Type":"application/json"},data=json.dumps({"path":"/v2/posting/fbs/act/list","body":{"limit":50,"filter":{"date_from":begin.isoformat(),"date_to":end.isoformat()}}}).encode())
try:
 with urllib.request.urlopen(req,timeout=55) as response:data=json.load(response)
except urllib.error.HTTPError as e:data={"error":"HTTP_"+str(e.code)}
db.put("fbs_document_chain:ozon:api_inventory:v1",{"at":now(),"response":data})
print(json.dumps({"saved":True,"document_writes":0}))
