"""Execute the exact failed human question through the analyst; no TG or WB writes."""
import os,json,copy
from datetime import datetime,timezone
import requests
from conversion_watches import runtime,saved_network_guard
from china_model_transport import ModelResponseError

def main():
 w=runtime();jobs=w.db('GET','business_agent_jobs',params={'id':'eq.87','agent_id':'eq.china','chat_id':'eq.-1004342917488','select':'*'})
 if len(jobs)!=1 or jobs[0].get('answer') is not None or jobs[0]['status']!='failed':raise RuntimeError('Original unanswered failed question required')
 job=jobs[0];history=w.db('GET','business_agent_jobs',params={'agent_id':'eq.china','chat_id':'eq.-1004342917488','sender_id':'eq.'+str(job['sender_id']),'status':'eq.done','id':'lt.87','select':'id,request_text,answer,tool_trace','order':'id.desc','limit':4}) or [];history.reverse()
 network=[];original=requests.sessions.Session.request
 def bounded(session,method,url,*args,**kwargs):
  from urllib.parse import urlparse
  u=urlparse(url);method=method.upper()
  if u.hostname=='api.telegram.org':raise PermissionError('No Telegram in diagnostic')
  if u.hostname and 'wildberries.ru' in u.hostname and method!='GET' and not (method=='POST' and u.path=='/api/advert/v1/bids/min'):raise PermissionError('No WB writes in diagnostic')
  network.append(dict(host=u.hostname,path=u.path,method=method))
  return original(session,method,url,*args,**kwargs)
 requests.sessions.Session.request=bounded
 try:
  with saved_network_guard():
   try:
    answer,trace=w.saved_question(job,history);status='answered';error=None
   except ModelResponseError as ex:
    status='model_blocked';answer=None;trace=[];error=dict(status=ex.status,retryable=ex.retryable,retry_after=ex.retry_after,details=ex.details)
   audit=dict(status=status,job_id=87,answer=answer,trace=trace,error=error,network=network,run_id=os.environ.get('GITHUB_RUN_ID'),observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_sends=0)
   w.save('china_agent:decline_verification:v1:87',audit)
   print(json.dumps(dict(status=status,job_id=87,wb_writes=0,telegram_sends=0)))
 finally:requests.sessions.Session.request=original

if __name__=='__main__':main()
