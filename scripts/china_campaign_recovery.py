"""One explicitly selected recovery: lower existing bids, deposit once, then resume."""
import copy
from datetime import datetime,timezone

def execute(*args,**kwargs):
 try:return _execute(*args,**kwargs)
 except AssertionError as error:raise ValueError(str(error)or'Recovery preflight failed')from None
def _execute(io,item,state,save,req,campaign,budget):
 if state.get('steps'):raise ValueError('Existing recovery journal; readback/manual review only, no replay')
 from china_morning_readiness import current_prices,published_stock
 from china_moysklad_read import read_stock
 cid=item['campaign_id'];e=item['recovery_evidence'];before=campaign(cid)
 assert item['kind']=='recover_campaign' and before['status']==11,'Recovery requires paused campaign'
 assert before['currency']=='CNY' and before['bid_type']=='manual' and before['settings']['payment_type']=='cpc'
 assert cid not in (40811856,) and not ({1473245494,1473245510}&{n['nm_id']for n in before['nm_settings']}),'Protected campaign/product'
 assert e['period_to']<datetime.now(timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date().isoformat()
 assert e['modeled_after_ads_cny']>0 and e['stress_after_ads_cny']>0 and e['preliminary']is True
 assert 0<=(datetime.now(timezone.utc)-datetime.fromisoformat(e['observed_at'].replace('Z','+00:00'))).total_seconds()<=24*3600,'Recovery economics expired'
 actual={str(n['nm_id']):n['bids_kopecks']for n in before['nm_settings']}
 assert actual==e['expected_bids'],'Recovery composition/bids changed'
 hold=(io.get('china_agent:budget_owner_policy:v1')or{}).get('do_not_fund',{}).get(str(cid))
 assert not hold or hold==item.get('supersedes_temporary_hold'),'New owner budget hold'
 zone=item['placement'];ids=sorted(map(int,actual))
 quote=req('/api/advert/v1/bids/min','POST',dict(advert_id=cid,nm_ids=ids,payment_type='cpc',placement_types=['search'if zone=='search'else'recommendation']))
 minima={r['nm_id']:next((v['value']for v in r['bids']if v['currency']=='CNY'and v['type']==('search'if zone=='search'else'recommendation')),None)for r in quote['bids']}
 keep=item.get('keep_existing_bids')is True
 assert set(minima)==set(ids) and all(type(minima[n])is int and 0<minima[n]<=item['target_minor']and (item['target_minor']==actual[str(n)][zone]if keep else item['target_minor']<actual[str(n)][zone])for n in ids),'Recovery minimum changed'
 prices=current_prices(io,ids);pub=published_stock(io,prices,ids);stock=read_stock([r['article']for r in prices['rows']]);stocks={r['article'].casefold():r for r in stock['rows']}
 assert stock['coverage_complete']and not pub['missing_nm_ids']and {r['nm_id']for r in prices['rows']}==set(ids),'Fresh recovery coverage incomplete'
 cost_increase_rub=0
 for r in prices['rows']:
  old=e['member_inputs'][str(r['nm_id'])];s=stocks[r['article'].casefold()]
  assert r['seller_price']==old['price']and s['price']>0 and s['stock']-s['reserve']>0 and pub['amounts'][str(r['nm_id'])]>0,'Recovery price/stock changed: '+r['article']
  cost_increase_rub+=max(0,s['price']/100-old['cost'])
 if cost_increase_rub:
  from urllib.parse import quote
  fx=e.get('fx_rub_per_cny')
  if fx is None:
   day=datetime.fromisoformat(e['observed_at'].replace('Z','+00:00')).astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date().isoformat()
   source='china_agent:advertising_source:'+day+':v2'
   rows=io.db('telegram_api_cache?cache_key=eq.'+quote(source,safe='')+'&select=rate:payload->full_growth_inputs->fx->rub_per_cny')
   fx=float(rows[0]['rate'])
  assert fx>0,'Verified model FX missing'
  # Worst-case all historical attributions carry every positive cost delta,
  # with buyout=100%; no credit for decreases or new orders is introduced.
  order_count=e.get('attributed_orders')
  if order_count is None:
   assert e.get('source_key'),'Recovery attribution source missing'
   raw=io.db('telegram_api_cache?cache_key=eq.'+quote(e['source_key'],safe='')+'&select=stats:payload->inputs->stats')
   matched=[r for r in raw[0]['stats']if r['advertId']==cid];assert len(matched)==1
   days=[d for d in matched[0]['days']if e['period_from']<=d['date'][:10]<=e['period_to']]
   assert days,'Recovery attribution window missing'
   order_count=sum(d['orders']for d in days)
  delta=order_count*cost_increase_rub/fx
  assert e['modeled_after_ads_cny']-delta>0 and e['stress_after_ads_cny']-delta>0,'Current COGS no longer supports the approved stress model'
  state['cost_revalidation']=dict(positive_increase_rub=cost_increase_rub,worst_case_model_delta_cny=delta,attributions_upper_bound=order_count,fx_rub_per_cny=fx)
 state.update(before=before,before_budget=budget(cid),steps=[]);save()
 assert state['before_budget']==item['balance_before'],'Campaign already funded; refresh recovery'
 cfg=req('/api/advert/v1/config');wallet=req('/adv/v1/balance');amount=item['amount_cny']
 assert cfg['currency']==wallet['currency']=='CNY'and cfg['minTopUp']<=amount*100
 source=0 if wallet.get('balance',0)>=amount else 1 if wallet.get('net',0)>=amount else None
 assert source is not None,'Insufficient CNY wallet'
 expected=copy.deepcopy(before)
 def same(got,status):
  return got['status']==status and all(got[k]==expected[k]for k in ['id','currency','bid_type','settings','nm_settings'])
 def step(label,path,method,body,verify):
  s=dict(id=label,status='submitting',request=dict(path=path,method=method,body=body));state['steps'].append(s);state['status']='submitting';save()
  try:
   s['response']=req(path,method,body);s['status']='accepted';state['wb_writes']=state.get('wb_writes',0)+1;save()
   for _ in range(20):
    if verify():
     s.update(status='verified',verified_at=datetime.now(timezone.utc).isoformat());state['status']='preflight';save();return
    __import__('time').sleep(3)
   raise ValueError('Recovery readback mismatch')
  except Exception:
   s['status']='uncertain';state['status']='uncertain';save();raise
 assert same(campaign(cid),11),'Campaign changed before lowering'
 if keep:
  state['steps'].append(dict(id='bids_unchanged',status='verified',read_only=True,verified_at=datetime.now(timezone.utc).isoformat()));save()
 else:
  for n in expected['nm_settings']:n['bids_kopecks'][zone]=item['target_minor']
  body=dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=nm,placement=zone,bid_kopecks=item['target_minor'])for nm in ids])])
  step('bids','/api/advert/v1/bids','PATCH',body,lambda:same(campaign(cid),11))
 assert budget(cid)==state['before_budget']and same(campaign(cid),11),'State changed before deposit'
 step('fund','/adv/v1/budget/deposit?id='+str(cid),'POST',dict(sum=amount,type=source),lambda:same(campaign(cid),11)and budget(cid)>=state['before_budget']+amount)
 assert same(campaign(cid),11)and budget(cid)>0,'Recovery prerequisites not verified'
 step('resume','/adv/v0/start?id='+str(cid),'GET',None,lambda:same(campaign(cid),9))
 state.update(status='verified',after=campaign(cid),after_budget=budget(cid),verified_at=datetime.now(timezone.utc).isoformat());save()
 # This exact human-confirmed restart replaces only its old temporary hold.
 # A newer/different owner hold remains intact; this is no standing funding grant.
 if hold:
  try:
   policy=io.get('china_agent:budget_owner_policy:v1')or{}
   if policy.get('do_not_fund',{}).get(str(cid))==hold:
    del policy['do_not_fund'][str(cid)]
    policy['released_temporary_hold_'+str(cid)]=dict(released_at=state['verified_at'],source='explicit_button_confirmed_recovery',before_hold=hold,verified_campaign_id=cid,grants_standing_funding_permission=False)
    io.put('china_agent:budget_owner_policy:v1',policy)
  except Exception:
   state['policy_reconciliation_required']=True;save()
 return state['wb_writes']
