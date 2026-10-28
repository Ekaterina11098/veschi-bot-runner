"""Download one explicitly requested complete weekly report; preserve raw rows privately."""
import os,json,time,gzip,urllib.request,urllib.error
import fbs_document_chain as m
db=m.Cache(m.Transport());root=os.environ["WEEKLY_REVIEW_ROOT"];req=db.get(root+"request:v1")
proof={"at":m.now(),"status":"reading","report_id":req["report_id"],"cabinet":req["cabinet"],"chunks":[]}
db.put(root+"source_proof:v1",proof)
cursor=0;seen=set();total=0;currencies=set();first=None
while True:
 request=urllib.request.Request("https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed/"+str(req["report_id"]),data=json.dumps({"limit":100000,"rrdId":cursor}).encode(),method="POST",headers={"Authorization":os.environ[req["token_env"]],"Content-Type":"application/json","Accept":"application/json","Accept-Encoding":"gzip"})
 status=0;data=None
 for attempt in range(3):
  try:
   with urllib.request.urlopen(request,timeout=90) as response:
    status=response.status;raw=response.read()
    if response.headers.get("Content-Encoding")=="gzip":raw=gzip.decompress(raw)
    data=json.loads(raw) if raw else []
   break
  except urllib.error.HTTPError as e:
   status=e.code
   if status not in (429,500,502,503,504) or attempt==2:break
   time.sleep(61)
 if status==204 or (status==200 and data==[]):
  proof["pagination_exhausted"]=True;break
 if status!=200:proof.update(status="source_error",http_status=status);db.put(root+"source_proof:v1",proof);raise m.Stop("Report source unavailable")
 rows=data if isinstance(data,list) else data.get("data",data.get("rows",[]))
 if not isinstance(rows,list) or not rows:raise m.Stop("Unexpected report representation")
 if first is None:first=rows[0];proof["keys"]=list(first);proof["sample"]=first
 for row in rows:
  rid=row.get("rrdId",row.get("rrd_id"))
  if rid in seen:raise m.Stop("Repeated report row identity")
  seen.add(rid)
  for key,value in row.items():
   if "currenc" in key.lower() and value is not None:currencies.add(str(value))
 for offset in range(0,len(rows),250):
  key=root+"source_rows:"+str(total+offset)
  db.put(key,rows[offset:offset+250]);proof["chunks"].append({"key":key,"rows":len(rows[offset:offset+250])})
 total+=len(rows);cursor=rows[-1].get("rrdId",rows[-1].get("rrd_id"))
 if not cursor:raise m.Stop("Missing report cursor")
 proof.update(rows=total,last_rrd_id=cursor,currencies=sorted(currencies));db.put(root+"source_proof:v1",proof)
 time.sleep(61)
proof.update(status="complete",rows=total,currencies=sorted(currencies),completed_at=m.now());db.put(root+"source_proof:v1",proof)
print(json.dumps({"status":proof["status"],"rows":total,"pages":len(proof["chunks"])}))
