"""Private, read-only live verification. Never delivers Telegram or executes WB changes."""
import copy,json,os
from datetime import datetime,timezone
import requests
from china_analytic_dialog import POLICY,answer
from conversion_watches import runtime,saved_network_guard
from china_experience import decision_context

def main():
 w=runtime();original_get=w.get
 w.get=lambda key:dict(enabled=True,model='gpt-6.1-sol') if key==POLICY else original_get(key)
 network=[];original=requests.sessions.Session.request
 def bounded(session,method,url,*args,**kwargs):
  from urllib.parse import urlparse
  u=urlparse(url);method=method.upper()
  if u.hostname=='api.telegram.org':raise PermissionError('No Telegram delivery in verification')
  if u.hostname and 'wildberries.ru' in u.hostname and method!='GET' and not (method=='POST' and u.path=='/api/advert/v1/bids/min'):raise PermissionError('No WB writes in verification')
  network.append(dict(host=u.hostname,path=u.path,method=method))
  return original(session,method,url,*args,**kwargs)
 requests.sessions.Session.request=bounded
 try:
  with saved_network_guard():
   context=decision_context(w)
   events=context['experiences']
   assert any(1473243891 in e.get('action',{}).get('nm_ids',[]) and e['action'].get('after')==42 for e in events),'Verified bid change not imported'
   assert 1473243891 in context['recent_changed_nm_ids'],'Recent change not applied to cooldown'
   assert any(e.get('advertising_outcome')=='negative' for e in events),'Negative experience missing'
   results=[]
   for idx,text in enumerate(['Что уже сделано со ставкой 0-NoelBag-green? Можно ли сейчас ещё повысить ставку?','Кандидаты в РК: кого сейчас можно добавить? Учти отрицательный опыт и изменения условий.']):
    job=dict(id=900000001+idx,agent_id='china',chat_id=-1004342917488,sender_id=5122667182,request_text=text,tool_trace=[],created_at=datetime.now(timezone.utc).isoformat())
    value,trace=answer(w,job,[])
    memory=next(t for t in trace if t['name']=='experience_context')
    calculation=next(t for t in trace if t['name']=='get_growth_candidates')
    w.save('china_agent:memory_verification_probe:v1',dict(question=text,answer=value,trace=trace,observed_at=datetime.now(timezone.utc).isoformat()))
    assert calculation['result'].get('status')=='complete','Candidate calculation incomplete; inspect private probe'
    assert calculation['result'].get('memory_used') is True
    assert memory['result']['total_events']>0
    assert not any(r['nm_id']==1473243891 for r in calculation['result']['rows']),'Repeated bid raise proposed during cooldown'
    results.append(dict(question=text,answer=value,tool_names=[t['name'] for t in trace],calculation=calculation['result'],memory_events=memory['result']['total_events']))
   from china_agent_reports import make,photo,daily_loss
   report_job=dict(id=900000003,chat_id=-1004342917488)
   report=make(w,report_job,'advertising',repeat=True)
   w.active_question_id=report_job['id'];assert photo(w,report_job['chat_id'],report['marker'])[0]
   assert report['execution_authorized'] is False
   assert daily_loss()=='delivered','Expected existing daily receipt; no duplicate report may be sent'
   audit=dict(status='verified',observed_at=datetime.now(timezone.utc).isoformat(),run_id=os.environ.get('GITHUB_RUN_ID'),model='gpt-6.1-sol',cases=results,network=network,reports=dict(explicit_repeat_prepared=True,schedule_identity_unchanged=True,existing_daily_receipt_respected=True),wb_writes=0,telegram_sends=0,confirmation_required=True)
   w.save('china_agent:memory_live_verification:v1',audit)
   print(json.dumps(dict(status='verified',cases=len(results),model=audit['model'],wb_writes=0,telegram_sends=0,memory_events=len(events))))
 finally:requests.sessions.Session.request=original

if __name__=='__main__':main()
