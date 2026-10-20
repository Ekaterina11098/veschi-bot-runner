import datetime as d
from fbs_document_chain import *
from fbs_ozon_api import ozon
t=Transport();db=Cache(t);end=d.datetime.now(d.timezone.utc);begin=end-d.timedelta(days=7)
report={"at":now(),"errors":[]}
try:
 acts=ozon("/v2/posting/fbs/act/list",{"limit":50,"filter":{"date_from":begin.date().isoformat(),"date_to":end.date().isoformat()}})
 report["acts"]=acts
 latest=acts["result"][0]
 answer=ozon("/v2/posting/fbs/act/get-postings",{"id":latest["id"]})
 report["act_postings"]=answer
 values=answer.get("result",[])
 if isinstance(values,dict):values=values.get("postings",[])
 if values and isinstance(values[0],dict) and values[0].get("posting_number"):
  report["posting_example"]=ozon("/v3/posting/fbs/get",{"posting_number":values[0]["posting_number"],"with":{"analytics_data":False,"financial_data":False}})
except Exception as e:report["errors"].append(str(e) if isinstance(e,Stop) else type(e).__name__)
db.put("fbs_document_chain:ozon:detail_inventory:v1",report)
print("Private act grouping inspection saved; no document writes")
