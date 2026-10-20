import os,json,urllib.request,urllib.error
from fbs_document_chain import Stop
def ozon(path,body):
 if path not in {"/v2/posting/fbs/act/list","/v2/posting/fbs/act/get-postings","/v3/posting/fbs/get"}:raise Stop("Ozon endpoint is not read-only allowlisted")
 request=urllib.request.Request(os.environ["SUPABASE_URL"].rstrip("/")+"/functions/v1/fbs-ozon-read",method="POST",headers={"x-fbs-backend-key":os.environ["SUPABASE_SECRET_KEY"],"Content-Type":"application/json"},data=json.dumps({"path":path,"body":body}).encode())
 try:
  with urllib.request.urlopen(request,timeout=55) as response:answer=json.load(response)
 except urllib.error.HTTPError as error:raise Stop("Ozon gateway HTTP_"+str(error.code)) from None
 if answer.get("upstream_status")!=200:raise Stop("Ozon API HTTP_"+str(answer.get("upstream_status"))+" "+str(answer.get("data",{}).get("message","validation failure")))
 return answer["data"]
