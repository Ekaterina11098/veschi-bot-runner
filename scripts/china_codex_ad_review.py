"""Free-dialog maintenance review -> exact reply-bound native actions. No WB writes/sends."""
import copy,json,re
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
ROOT='china_agent:codex_ad_review:v1:'
def stamp():return datetime.now(timezone.utc).isoformat()
def request(value):
 if set(value)-{'kind','campaign_ids'} or value.get('kind')!='review_advertising':raise ValueError('Invalid maintenance request')
 ids=value.get('campaign_ids',[])
 if not isinstance(ids,list) or len(ids)>50 or len(set(ids))!=len(ids) or any(type(n)is not int or n<=0 for n in ids):raise ValueError('Exact campaign scope required')
 return dict(kind='review_advertising',campaign_ids=ids)
def review(io,day,campaign_ids=(),refresh=True):
 from china_advertising_v2 import build,http
 from china_advertising_cards import enhance
 from china_advertising_economic_review import apply
 source_key='china_agent:advertising_source:'+day+':v2'
 s=copy.deepcopy(io.get(source_key)or{})
 end=(datetime.fromisoformat(day).date()-timedelta(days=1)).isoformat()
 if (s.get('cabinet')!='token_3' or s.get('status')!='complete' or s.get('period_to')!=end) and refresh:
  from china_advertising_v2 import collect
  s=copy.deepcopy(collect(io,day))
 if s.get('cabinet')!='token_3' or s.get('status')!='complete' or s.get('period_to')!=end:raise ValueError('Нет полного источника рекламы по '+end+' после попытки сбора; не нулевые данные')
 states={c['id']:c for b in s['batches'].values()for c in b['campaigns'].get('adverts',[])}
 ids=list(campaign_ids)or sorted(cid for cid,c in states.items()if c.get('status')==9)
 if not ids or len(ids)>50 or any(cid not in states for cid in ids):raise ValueError('Campaign scope missing or exceeds50')
 registry=io.get('china_agent:verified_campaign_state:v1')or{}
 for cid,key in registry.items():
  receipt=io.get(key)or{}
  if receipt.get('status')=='verified' and receipt.get('after',{}).get('id')==int(cid):
   s.setdefault('executions',[]).append(dict(cache_key=key,payload=receipt))
   if int(cid)in ids:states[int(cid)]=copy.deepcopy(receipt['after'])
 if refresh:
  fresh=http(io,'/api/advert/v2/adverts?ids='+','.join(map(str,ids))).get('adverts',[])
  if {c['id']for c in fresh}!=set(ids):raise ValueError('Incomplete current campaign readback')
  states.update({c['id']:c for c in fresh})
 raw={r['advertId']:r for b in s['batches'].values()for r in b.get('stats',[])}
 missing=[cid for cid in ids if cid not in raw]
 if missing and refresh:
  records=http(io,'/adv/v3/fullstats?ids='+','.join(map(str,missing))+'&beginDate='+s['period_from']+'&endDate='+s['period_to'])
  if not isinstance(records,list):raise ValueError('WB did not return completed statistics for campaigns '+','.join(map(str,missing)))
  raw.update({r['advertId']:r for r in records})
 if any(cid not in raw for cid in ids):raise ValueError('Missing completed advertising statistics, not zero')
 budgets={r['advertId']:r for b in s['batches'].values()for r in b.get('budgets',{}).get('adverts',[])if r}
 if any(cid not in budgets for cid in ids):raise ValueError('Dated campaign budgets missing')
 s['ids']=ids;s['batches']={'0':dict(campaigns={'adverts':[states[cid]for cid in ids]},stats=[raw[cid]for cid in ids],budgets={'adverts':[budgets[cid]for cid in ids]})}
 # The native engine calculates all directions; maintenance contains only cost controls.
 rough=enhance(build(s),s)
 selected=sorted({r['nm']for c in rough['campaigns']for r in c.get('focus',[])if not r.get('pending_first_day')})
 if len(selected)>100:raise ValueError('Exact economics cohort exceeds100; narrow campaign scope')
 if refresh and selected:
  from china_morning_readiness import enrich_economics
  s=enrich_economics(io,s,rough,day)
  if s.get('morning_fresh_inputs',{}).get('errors'):raise ValueError('Не получены данные: '+','.join(s['morning_fresh_inputs']['errors']))
  from china_morning_readiness import current_prices,published_stock
  pub=published_stock(io,current_prices(io,selected),selected)
  if pub['missing_nm_ids']:raise ValueError('Published WB stock coverage incomplete')
  for nm,e in s.get('economics',{}).get('rows',{}).items():
   e.update(published_stock=pub['amounts'].get(str(nm)),published_stock_observed_at=pub['observed_at'])
 minima={}
 for c in rough['campaigns']:
  wanted=[r['nm']for r in c.get('focus',[])if r['nm']in {n['nm_id']for n in states[c['id']]['nm_settings']}and not r.get('pending_first_day')]
  if not wanted or c['status']!=9 or c['payment']!='cpc':continue
  zone='search'if c['zone']=='поиск'else'recommendation'
  if refresh:
   response=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=c['id'],nm_ids=wanted,payment_type='cpc',placement_types=[zone]))
   for n in response.get('bids',[]):
    quotes=[b['value']for b in n.get('bids',[])if b.get('currency')=='CNY'and b.get('type')==zone]
    if len(quotes)!=1:raise ValueError('Ambiguous exact campaign minimum')
    minima[str(c['id'])+':'+str(n['nm_id'])]=quotes[0]
  else:minima.update(s.get('review_minima',{}))
  if any(str(c['id'])+':'+str(n)not in minima for n in wanted):raise ValueError('Exact minima incomplete')
 bundle=apply(enhance(build(s,minima),s),s,minima)
 actions=[];rows=[]
 for c in bundle['campaigns']:
  for r in c.get('focus',[]):
   action=r.get('action');period=(r.get('comparison')or{}).get('after')or r['period']
   rows.append(dict(campaign_id=c['id'],article=r['article'],nm_id=r['nm'],period=period,decision=r['decision'],reason=r['reason']))
   if action and (action['kind']=='ad_exclude_sku'or action['kind']=='ad_set_bid'and action['target_minor']<action['old_minor']):
    step=s['config'].get('cpcStep')
    if action['kind']=='ad_set_bid'and(type(step)is not int or step<=0 or action['target_minor']%step):raise ValueError('Bid step not verified')
    if action['nm_id']in (1473245494,1473245510):continue
    withdrawn=(io.get('china_agent:analysis_backend:v1')or{}).get('owner_withdrawn_actions',[])
    if any(all(action.get(k)==x.get(k)for k in ('kind','campaign_id','nm_id'))for x in withdrawn):continue
    actions.append(dict(action,review_evidence=dict(period_to=s['period_to'],source_key=source_key,economics=r.get('economics'),minimum=minima.get(str(c['id'])+':'+str(r['nm'])))))
 blockers=bundle.get('economic_review_blockers',[])
 if blockers:raise ValueError('Неполная экономика: '+','.join(str(r['article'])for r in blockers))
 return dict(status='reviewed',actions=actions,rows=rows,days=bundle['days'],campaign_ids=ids,source_key=source_key,observed_at=stamp(),wb_writes=0,telegram_sends=0,coverage='requested_campaigns',directions=dict(reduce_exclude='reviewed',raise_add='separate_growth_preparation_not_implicitly_authorized'))
def prepare(w,job,value,io=None):
 value=request(value)
 if io is None:
  from china_loss_execute import IO
  io=IO()
 key=ROOT+str(job['id']);prior=w.get(key)
 if prior:return prior
 day=datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()
 result=review(io,day,value['campaign_ids'])
 from china_loss_control import CHAT,BOT,PLAN,digest
 pid='dialog-review-'+str(job['id']);items=result['actions']
 text='Разбор рекламы за '+', '.join(result['days'])+'.\n'
 if items:
  text+='| РК | Товар | Рекомендация |\n|---|---|---|\n'
  for item in items:
   action='Исключить из этой РК'if item['kind']=='ad_exclude_sku'else 'Снизить '+str(item['old_minor']/100)+' → '+str(item['target_minor']/100)+' CNY'
   text+='| '+str(item['campaign_id'])+' | '+item['article']+' | '+action+' |\n'
  text+='Ответьте «Сделай всё» на этот план. До подтверждения изменений нет.'
  p=dict(plan_id=pid,execution_kind='daily_ad_actions_v2',family='dialog_review',items=items,plan_sha256=digest(items),created_at=stamp(),expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),report_message_ids=[],chat_id=CHAT,bot_id=BOT,source_job_id=job['id'],price_changes=False,budget_writes=False)
  if not w.save(PLAN+pid,p,insert=True):raise ValueError('Review plan already exists with different identity')
 else:text+='Новых готовых снижений или исключений нет. Уже выполненное не повторяю; новые действия — после оценки следующего полного дня.'
 result.update(plan_id=pid if items else None,answer=text,source_job_id=job['id'])
 if not w.save(key,result,insert=True):raise ValueError('Review save conflict')
 return result
def bind(w,job_id,message_ids,answer):
 result=w.get(ROOT+str(job_id))or{}
 if not result.get('plan_id'):return
 if result['answer']!=answer:raise ValueError('Delivered review text changed')
 from china_loss_control import PLAN,CHAT,digest
 from china_daily_ad_actions import BIND
 p=w.get(PLAN+result['plan_id'])
 if not p or digest(p['items'])!=p['plan_sha256']:raise ValueError('Review hash changed')
 for mid in message_ids:
  if type(mid)is not int:raise ValueError('Actual delivered message required')
  p['report_message_ids']=sorted(set(p['report_message_ids']+[mid]))
  key=BIND+str(mid);value=dict(plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],chat_id=CHAT,family='dialog_review')
  old=w.get(key)
  if old and old!=value:raise ValueError('Existing message binding changed')
  if not old:w.save(key,value,insert=True)
 w.save(PLAN+p['plan_id'],p)
 from china_report_keyboard import attach
 artifact=w.get('china_agent:table_png:v1:'+str(job_id))or{}
 expected=len(artifact.get('parts',[]))
 if message_ids and (not expected or len(message_ids)>=expected):attach(w,p,message_ids[-1])
