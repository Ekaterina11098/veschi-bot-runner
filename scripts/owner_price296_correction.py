"""Repair a false empty price recommendation report; read-only preflight and bound delivery only."""
import copy,json,requests,uuid
from datetime import datetime,date,timedelta,timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
from china_loss_execute import IO
from china_price_period import period
from china_buyer_price_forecast import build,forecast
from china_price_delivery import deliver,rows
from china_price_review_guard import protected_repeats
K='china_agent:owner_price296_correction:2026-11-11:v1'
def run():
 io=IO()
 class Worker:
  def __init__(self):
   self.day=date(2026,11,11);self.now=datetime.now(ZoneInfo('Europe/Moscow'));assert self.now.date()==self.day
   self.mode='morning-corrected296';self.chat=-1004342917488;self.audit={};self.uncertain=False;self.telegram_cooldown=0
   self.original_http=requests.sessions.Session.request
  def get(self,k):return io.get(k)
  def db(self,method,table,params=None,body=None,prefer=None):
   return io.db(table+('?' +urlencode(params)if params else''),method,body,prefer)
  def patch(self,body):
   result=io.db('business_agent_jobs?id=eq.'+str(self.job['id']),'PATCH',body,'return=representation');assert len(result)==1
   self.job=result[0];return result
 w=Worker();prior=io.get(K)
 if prior and prior.get('status')=='sent':
  print('Already corrected; no duplicate');return
 old=io.get('china_agent:price_delivery:v2:2026-11-11:morning:part:0')
 assert old['status']=='sent'and old['message_id']==869
 if prior is None:
  state=w.get('china_agent:demand_watch:v1');latest=state['latest']
  assert latest['period_from']=='2026-11-07'and latest['period_to']=='2026-11-10'and latest['candidate_count']==11
  source,marker=period(w,w.day-timedelta(days=1),w.day-timedelta(days=1))
  basis=build(source,marker,w.get('china_agent:prices:v1'),w.day);assert basis['status']=='available'
  draft=[];excluded=[]
  for nm,r in sorted(latest['results'].items(),key=lambda t:t[1].get('article','')):
   if r.get('action')!='raise':continue
   p=state['price_history'][nm]['price'];article=r['article']
   current=p['current_cny'];target=p['target_cny'];buyer=basis['rows'].get(nm)
   predicted=forecast(basis,nm,article,current,target,w.day)
   if not buyer or predicted is None:excluded.append(dict(nm_id=nm,article=article,reason='buyer_forecast_unavailable'));continue
   row='Повышение · '+article+' Продавец: '+format(current,'g')+' → '+format(target,'g')+' ¥\nПокупатель: '+str(round(float(buyer['buyer_rub'])))+' → '+str(predicted)+' ₽'
   assert protected_repeats(w,{'row':row})=={'row'}
   draft.append(row)
  assert len(draft)+len(excluded)==11
  assert draft
  answer='\n\n'.join(draft)+'\n\nСнижение: нет готовых рекомендаций'
  trace=[dict(name='china_price_daily_report',report_date=str(w.day),period_from='2026-11-07',period_to='2026-11-10',ready_rises=len(draft),source_snapshot_id=21856,execution_authorized=False),dict(name='owner_price_review_correction',source_job_id=296,reason='false_empty_from_hold_rule_applied_to_repeat_raises',source_key=K)]
  rec=dict(status='prepared',original_delivery=old,original_job=296,source_state=dict(latest=latest,price_history={nm:state['price_history'][nm]for nm,r in latest['results'].items()if r.get('action')=='raise'}),buyer_basis=basis,answer=answer,excluded=excluded,trace=trace,wb_writes=0)
  assert io.create(K,rec);prior=rec
 if not prior.get('job_id'):
  jobs=io.db('business_agent_jobs?on_conflict=agent_id,update_id','POST',dict(agent_id='china',update_id=-980001111296,chat_id=w.chat,sender_id=5122667182,request_text='/china_morning_pair_candidates',status='running',attempts=1,lease_until=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat(),lease_token=str(uuid.uuid4()),answer=prior['answer'],tool_trace=prior['trace']),'resolution=ignore-duplicates,return=representation')
  if not jobs:jobs=io.db('business_agent_jobs?agent_id=eq.china&update_id=eq.-980001111296&select=id,answer,tool_trace,status')
  assert len(jobs)==1
  prior.update(job_id=jobs[0]['id']);io.put(K,prior)
 w.job=io.db('business_agent_jobs?id=eq.'+str(prior['job_id'])+'&select=id,answer,tool_trace,status')[0]
 deliver(w)
 final=io.get('china_agent:price_delivery:v2:2026-11-11:morning-corrected296');assert final['status']=='sent'and final['message_ids']
 actual=io.get('china_agent:price_delivery:v2:2026-11-11:morning-corrected296:prepared')
 assert actual['selection_count']>=1 and actual.get('reply_markup')and actual.get('button_registry')
 for key in final['receipt_keys']:
  part=io.get(key);assert part['status']=='sent'and part['receipt'].get('reply_markup')==actual['reply_markup']
 prior.update(status='sent',delivery=final,selection_count=actual['selection_count'],preflight=w.audit.get('proposal_current_check'));io.put(K,prior)
 # Clarify the earlier false empty report in place; preserve its original receipt above.
 fixkey=K+':old_notice'
 if io.get(fixkey)is None:
  assert io.create(fixkey,dict(status='editing',message_id=869))
  r=io.tg('editMessageText',dict(chat_id=w.chat,message_id=869,text='Уточнение к ценовому отчёту10:32: вывод «нет готовых рекомендаций» был ошибочным. Исправленный отчёт с проверенными предложениями и кнопками — сообщение'+str(final['message_ids'][0])+'. Цены автоматически не менялись.'))
  assert r['message_id']==869 and r['chat']['id']==w.chat
  io.put(fixkey,dict(status='edited_verified',message_id=869,receipt=r))
 print(json.dumps(dict(status='sent',offers=actual['selection_count'],message_ids=final['message_ids'],wb_writes=0)))
if __name__=='__main__':run()
