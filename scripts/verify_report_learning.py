"""Read-only production acceptance and explicit owner-approved report memory."""
import os,json,copy,hashlib
from datetime import datetime,timezone
from urllib.parse import urlparse
import requests
from conversion_watches import runtime
from china_order_profit_forecast import calculate_inputs,collect
from china_question_feedback import clarification,acknowledgement_text
KEY='china_agent:report_learning_verification:v1:2026-10-24'
def main():
 original=requests.sessions.Session.request
 def guard(session,method,url,*a,**kw):
  u=urlparse(url);m=method.upper()
  if u.hostname=='api.telegram.org':raise PermissionError('No additional Telegram')
  if u.hostname and u.hostname.endswith('wildberries.ru'):
   if m!='GET' and not (m=='POST' and u.path in ['/api/analytics/v3/sales-funnel/products','/api/finance/v1/sales-reports/detailed']):raise PermissionError('Read-only WB')
  if u.hostname=='api.moysklad.ru' and m!='GET':raise PermissionError('Read-only MoySklad')
  if u.hostname==urlparse(os.environ['SUPABASE_URL']).hostname and m!='GET' and u.path not in ['/rest/v1/telegram_api_cache','/rest/v1/analytics_snapshots']:raise PermissionError('No jobs or business configuration changes')
  return original(session,method,url,*a,**kw)
 requests.sessions.Session.request=guard
 try:
  w=runtime();package=w.get('china_agent:report_learning_package:v1:2026-10-24')
  delivered=w.get('china_agent:approved_answer_replace:v1:88:profit_forecast')
  if not package or not delivered or delivered.get('delivery_status')!='sent' or delivered.get('old_message_status')!='deleted' or package['template']['sha256']!=delivered['sha256']:raise ValueError('Owner-approved template receipt missing')
  agreement=w.get('china_agent:agreements:v1')
  if not isinstance(agreement.get('agreements'),list):raise ValueError('Agreement schema')
  added=[r for r in package['rules'] if r not in agreement['agreements']]
  if added:
   agreement['agreements']+=added;agreement['revision']=int(agreement.get('revision',0))+1;w.save('china_agent:agreements:v1',agreement)
  if not all(r in w.get('china_agent:agreements:v1')['agreements'] for r in package['rules']):raise ValueError('Memory readback failed')
  w.save('china_agent:report_format:v1',package['template'])
  now=datetime.now(timezone.utc);job=dict(id=-2026102407,agent_id='china',chat_id=-1004342917488,sender_id=5122667182,request_text='Разбери падение заказов и прогноз прибыли за21-23октября2026. Только чтение; не отправляй вTelegram.',tool_trace=[dict(name='china_saved_question',message_id=0)])
  ask=clarification(dict(job,request_text='Дай отчет за вчера'),[],now)
  if not ask or '23.10.2026' not in ask:raise ValueError('Ambiguous report routing failed')
  if acknowledgement_text(dict(job,request_text='Дай отчет по продажам за вчера'))!='Принял, готовлю отчёт.':raise ValueError('Acknowledgement routing failed')
  # Replay the exact privately stored approved example with the reusable engine.
  raw=w.db('GET','analytics_snapshots',params={'id':'eq.19210','select':'id,payload,collected_at,period_from,period_to','limit':1})[0]
  source=raw['payload'][0]['data']['data']['data']
  products=[dict(nm_id=p['nm_id'],article=p['sa_name'],finished=p['finished_orders'],paid=p['is_payed'],returned=p['finish_as_return'],reported_pct=p.get('is_payed_percent_after_returns')) for p in source]
  stock=w.get('china_agent:analytic_read:v1:9e4056e823a5bfde339abb603e79046fcc37a63eecea08a6ee4eda999ad871d2')
  recovery=w.get('china_agent:profit_preview_inputs:v1:2026-10-21:2026-10-23:cost_recovery')
  original_inputs=w.get('china_agent:profit_preview_inputs:v1:2026-10-21:2026-10-23')
  grouped={}
  from datetime import timedelta
  msk=timezone(timedelta(hours=3))
  for o in original_inputs['orders']:
   day=str(datetime.fromisoformat(o['createdAt'].replace('Z','+00:00')).astimezone(msk).date())
   r=grouped.setdefault((o['nmId'],day),dict(nm_id=o['nmId'],article=o['article'],day=day,orders=0));r['orders']+=1
  base=dict(buyout=dict(rows=products,snapshot_id=raw['id'],period_from=raw['period_from'],period_to=raw['period_to'],observed_at=raw['collected_at']),stock=stock,history_costs=[],policy=w.get('china_agent:new_ad_economics_policy:v1'),finance=w.get('china_agent:wb_evidence:v1:finance:2026-09-23:2026-10-22'),funnel=[w.get('china_agent:wb_evidence:v1:funnel:'+d+':'+d) for d in ['2026-10-22','2026-10-23']])
  extra=dict(prices=w.get('china_agent:analytic_read:v1:c8d7c369ff8d0b2f8a06c0ebef442159a9b0beb0c50e2310ed614315ecf2f865'),ad_expenses=original_inputs['advertising'],days=['2026-10-21','2026-10-22','2026-10-23'],orders_observed_at=original_inputs['observed_at'])
  result=calculate_inputs(base,extra,list(grouped.values()),w.get('china_agent:expected_profit_delivery_model:v1'),recovery)
  approved=w.get('china_agent:decline_profit_preview:v1:2026-10-21:2026-10-23')
  if result['daily']!=approved['daily']:raise ValueError('Approved private fixture calculation changed')
  status=dict(status='fixture_verified',memory_revision=agreement['revision'],format_saved=True,clarification=ask,acknowledgement='Принял, готовлю отчёт.',fixture_orders=sum(d['created_orders'] for d in result['daily']),verified_at=now.isoformat(),wb_writes=0,telegram_sends=0)
  w.save(KEY,status)
  try:
   live=collect(w,job,'2026-10-21','2026-10-23')
   status.update(status='verified' if live['status']=='calculated_preliminary' else 'live_partial',live_source=live.get('source_key'),live_status=live['status'],live_gaps=live.get('gaps'),buyout_period=live.get('buyout_period'),daily=live.get('daily'),live_collected_at=datetime.now(timezone.utc).isoformat())
  except Exception as ex:
   status.update(status='live_blocked',error=type(ex).__name__,detail=str(ex)[:220] if isinstance(ex,(ValueError,RuntimeError)) else 'Source transport failed')
  w.save(KEY,status);print(json.dumps({k:status.get(k) for k in ['status','memory_revision','fixture_orders','error','wb_writes','telegram_sends']}))
  if status['status']!='verified':raise SystemExit(1)
 finally:requests.sessions.Session.request=original
if __name__=='__main__':
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner':raise SystemExit('Public runner only')
 main()
