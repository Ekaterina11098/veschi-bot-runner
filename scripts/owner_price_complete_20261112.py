"""Owner12Nov final combined price report: replace1001, never mutate WB or call a model."""
from datetime import date
import json,requests
from china_agent.morning_pair import PairWorker

def main():
 w=PairWorker('candidates')
 if w.day!=date(2026,11,12):raise RuntimeError('Dated owner completion expired')
 key='china_agent:owner_price_complete:2026-11-12:v1:delivered'
 old=w.get(key)
 if old:
  if old.get('status')!='edited':raise RuntimeError('Existing completion uncertain; no replay')
  print(dict(status='already_edited',message_id=1001));return
 preview=w.get('china_agent:owner_price_complete:2026-11-12:v1:preview')
 review=w.get('china_agent:daily_expected_candidates:2026-11-12:verify')
 assert preview['status']=='verified_preview' and preview['model_calls']==0 and preview['wb_writes']==0
 assert preview['answer'].endswith('Снижение: нет') and 'нет данных'not in preview['answer']
 assert review['status']=='complete_disclosed_forecast_model'
 assert not any(p.get('status')=='insufficient_economics'for p in review['products'])
 existing=w.get('china_agent:price_report_message:v1:1001')
 assert existing['status']=='sent' and existing['chat_id']==-1004342917488 and existing['report_job_id']==315
 pending=w.db('GET','business_agent_jobs',params=dict(agent_id='eq.china',id='gt.315',select='id,request_text,status'))
 assert not pending,'New requests require owner report-race review before replacement'
 w.save(key+':previous_binding',existing)
 w.manual=True;w.command='/china_owner_complete_price_report_20261112'
 w.update_id=-9200000000-(w.day-date(2020,1,1)).days
 w.delivery_mode='morning-complete-owner';w.price_control_review=review
 def prepared(preview=False):
  return globals_preview['answer'],[dict(name='china_price_daily_report',status='complete_orders',report_date=str(w.day),period_from='2026-11-08',period_to='2026-11-11',execution_authorized=False)]
 globals_preview=preview;w.prepare=prepared
 original=w.original_http
 def replace_report(session,method,url,*args,**kwargs):
  if url.startswith('https://api.telegram.org/') and url.endswith('/sendPhoto'):
   frozen=w.get('china_agent:price_delivery:v2:2026-11-12:morning-complete-owner:prepared')
   assert len(frozen['parts'])==1
   body=dict(kwargs['data']);assert int(body['chat_id'])==-1004342917488
   body['message_id']=1001
   body['media']=json.dumps(dict(type='photo',media='attach://photo',caption='Китай · цены · 12.11.2026. Повышение: 13 предложений. Снижение: готовых рекомендаций нет. Новая цена покупателя — прогноз. Изменения только после подтверждения.'),ensure_ascii=False)
   body.pop('caption',None)
   kwargs=dict(kwargs,data=body);url=url.rsplit('/',1)[0]+'/editMessageMedia'
  elif url.startswith('https://api.telegram.org/') and url.rsplit('/',1)[-1]in('sendMessage','sendDocument'):
   raise RuntimeError('Only replacement of report1001 is authorized here')
  return original(session,method,url,*args,**kwargs)
 w.original_http=replace_report
 try:
  w.run()
  root=w.get('china_agent:price_delivery:v2:2026-11-12:morning-complete-owner')
  assert root['status']=='sent' and root['message_ids']==[1001]
  old_registry_key='china_agent:price_buttons:v1:07211fdfc75b370c7ffd4b84'
  registry=w.get(old_registry_key)
  if registry:
   registry.update(status='superseded',superseded_by_job_id=w.job['id'],superseded_by_message_id=1001)
   w.save(old_registry_key,registry)
  w.save(key,dict(status='edited',message_id=1001,job_id=w.job['id'],method='editMessageMedia',receipt_key=root['receipt_keys'][0],audit=w.audit,model_calls=0,wb_writes=0,grants_action_permission=False))
  print(dict(status='edited',message_id=1001,job_id=w.job['id'],model_calls=0,wb_writes=0))
 finally:
  requests.sessions.Session.request=original
if __name__=='__main__':main()
