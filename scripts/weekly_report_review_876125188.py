"""Read-only lookup of two explicitly requested weekly WB reports."""
import os,json,time,gzip,urllib.request,urllib.error
from fbs_document_chain import Cache,Transport,now,Stop
db=Cache(Transport());root="weekly_report_review:876125188_876125192:"
proof={"at":now(),"status":"searching","attempts":[],"reports":{}}
def request(token,ident,cursor=0):
 req=urllib.request.Request("https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed/"+str(ident),
  data=json.dumps({"limit":100000,"rrdId":cursor}).encode(),method="POST",
  headers={"Authorization":token,"Content-Type":"application/json","Accept":"application/json","Accept-Encoding":"gzip"})
 try:
  with urllib.request.urlopen(req,timeout=60) as response:
   raw=response.read()
   if response.headers.get("Content-Encoding")=="gzip":raw=gzip.decompress(raw)
   return response.status,json.loads(raw) if raw else []
 except urllib.error.HTTPError as e:return e.code,None
for cabinet,number in (("ip","2"),("china","3"),("ooo","1")):
 token=os.environ["WB_TOKEN_"+number]
 status,data=request(token,876125188)
 proof["attempts"].append({"cabinet":cabinet,"status":status});db.put(root+"proof",proof)
 if status!=200 or not data:continue
 for ident in (876125188,876125192):
  if ident!=876125188:
   time.sleep(61);status,data=request(token,ident)
  rows=data if isinstance(data,list) else data.get("data",data.get("rows",[])) if isinstance(data,dict) else []
  if status!=200 or not isinstance(rows,list) or not rows:
   proof["reports"][str(ident)]={"status":status,"response_type":type(data).__name__};continue
  for offset in range(0,len(rows),250):db.put(root+str(ident)+":rows:"+str(offset),rows[offset:offset+250])
  last=rows[-1].get("rrdId",rows[-1].get("rrd_id"))
  exhausted=False
  if last:
   time.sleep(61);nextstatus,nextdata=request(token,ident,last)
   exhausted=nextstatus==204 or (nextstatus==200 and nextdata==[])
  proof["reports"][str(ident)]={"cabinet":cabinet,"rows":len(rows),"keys":list(rows[0]),"sample":rows[:1],"pagination_exhausted":exhausted,"last_rrd_id":last}
  db.put(root+"proof",proof)
 proof["status"]="found";break
else:proof["status"]="not_found_or_no_access"
proof["completed_at"]=now();db.put(root+"proof",proof)
print(json.dumps({"status":proof["status"],"report_count":len(proof["reports"])}))
