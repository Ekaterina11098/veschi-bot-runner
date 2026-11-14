"""Whole-campaign risk and bounded restart proposals, completed days only; no writes."""
import copy,math
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
PROTECTED={1473245494,1473245510}
def finite(v):return type(v)in(int,float)and math.isfinite(v)
def apply(io,bundle,source,minima):
 from china_advertising_v2 import http,history
 # Legacy arithmetic/unit callers without the complete report context are not a risk scan.
 if not bundle.get('day')or not bundle.get('days'):return copy.deepcopy(bundle)
 out=copy.deepcopy(bundle);now=datetime.now(timezone.utc);day=out['day'];days=out['days']
 states={c['id']:c for b in source['batches'].values()for c in b['campaigns']['adverts']}
 stats={c['advertId']:c for b in source['batches'].values()for c in b['stats']}
 models=(source.get('economics')or{}).get('rows',{});data=source.get('full_growth_inputs')or{}
 own={int(r['nm_id']):r for r in data.get('own',{}).get('rows',[])}
 fx=(data.get('fx')or{}).get('rub_per_cny');changes=history(source.get('executions',[]))
 holds=(io.get('china_agent:budget_owner_policy:v1')or{}).get('do_not_fund',{})
 def fresh(e):
  try:return all(0<=(now-datetime.fromisoformat(e[k].replace('Z','+00:00'))).total_seconds()<=24*3600 for k in ['observed_at','stock_observed_at','price_observed_at'])
  except (KeyError,TypeError,ValueError):return False
 def model(nm):
  e=models.get(str(nm),{});rate=e.get('fx_rub_per_cny',fx)
  if not fresh(e)or not all(finite(e.get(k))for k in ['expected_margin_before_ads_cny','buyout','own_cogs_rub','seller_price_cny','stock_free','logistics_cny']):return None
  if not finite(rate)or rate<=0:return None
  # A real zero own buyout is never replaced by the planned prior.
  if e.get('buyout_fallback')and e.get('sample_size',0)>0:return None
  o=own.get(nm,{});q=e['buyout'];sample=e.get('sample_size',0)
  delivery=max(e['logistics_cny'],(o.get('average_delivery_cost')or 0)/rate)
  reverse=(o.get('backwardlogisticsum')or 0)/sample/rate if sample else 0
  margin=e['expected_margin_before_ads_cny']-(delivery-e['logistics_cny'])-reverse
  stress=margin
  if sample<10 and q>.5:stress-=(q-.5)*(e['seller_price_cny']*(1-(e.get('commission_pct',20)+e.get('tax_pct',5)+e.get('payment_reserve_pct',0))/100)-e['own_cogs_rub']/rate)
  return e,margin,stress
 audit=[]
 for c in out['campaigns']:
  st=states.get(c['id']);raw=stats.get(c['id']);members={n['nm_id']for n in(st or{}).get('nm_settings',[])}
  if not st or not raw or st.get('status')not in(9,11)or st.get('bid_type')!='manual'or st.get('settings',{}).get('payment_type')!='cpc'or members&PROTECTED:continue
  zone='search'if st['settings']['placements'].get('search')else'recommendations';typ='search'if zone=='search'else'recommendation'
  closed=[d for d in raw.get('days',[])if d['date'][:10]in days and d['date'][:10]<day]
  if len(closed)<2:continue # Missing days remain missing, never synthesized as zero.
  spend=sum(d['sum']for d in closed);clicks=sum(d['clicks']for d in closed);orders=sum(d['orders']for d in closed)
  if spend<=0:continue
  bynm={};costs={};stable={}
  for d in closed:
   for app in d.get('apps',[]):
    for r in app.get('nms',[]):
     nm=r['nmId'];bynm[nm]=bynm.get(nm,0)+r.get('orders',0);costs[nm]=costs.get(nm,0)+r.get('sum',0)
     events=[datetime.fromisoformat(x['at'].replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()for x in changes if x.get('nm')==nm and x.get('kind')in('bid','price','added','returned')]
     if not events or d['date'][:10]>max(events):stable[nm]=stable.get(nm,0)+r.get('orders',0)
  if sum(bynm.values())!=orders:continue
  member_models={nm:model(nm)for nm in members};order_models={nm:model(nm)for nm,n in bynm.items()if n>0}
  if any(v is None for v in member_models.values())or st['status']==9 and any(v is None for v in order_models.values()):
   audit.append(dict(campaign_id=c['id'],status='missing_exact_economics'));continue
  pub=(data.get('published_stock')or{}).get('amounts',{})
  if st['status']==11 and any(v[0]['stock_free']<=0 or not finite(pub.get(str(nm),v[0].get('published_stock')))or pub.get(str(nm),v[0].get('published_stock'))<=0 for nm,v in member_models.items()):continue
  # Exact current minima are needed for pauses at the floor as well as restarts.
  if any(str(c['id'])+':'+str(nm)not in minima for nm in members):
   q=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=c['id'],nm_ids=sorted(members),payment_type='cpc',placement_types=[typ]))
   for row in q.get('bids',[]):
    values=[v['value']for v in row['bids']if v['type']==typ and v['currency']=='CNY']
    if len(values)==1:minima[str(c['id'])+':'+str(row['nm_id'])]=values[0]
  if any(type(minima.get(str(c['id'])+':'+str(nm)))is not int for nm in members):continue
  contribution=sum(bynm[nm]*v[1]for nm,v in order_models.items()if v is not None);net=contribution-spend
  floor_cost=sum(costs.get(nm,0)for nm in members if st['nm_settings'][next(i for i,n in enumerate(st['nm_settings'])if n['nm_id']==nm)]['bids_kopecks'][zone]<=minima[str(c['id'])+':'+str(nm)])
  evidence=dict(period_from=min(d['date'][:10]for d in closed),period_to=max(d['date'][:10]for d in closed),observed_at=source['observed_at'],modeled_after_ads_cny=net,spend_cny=spend,preliminary=True,unknown_costs=True,not_post_change_causal_verdict=True)
  action=None;decision=None
  if st['status']==9 and clicks>=100 and net<0 and floor_cost>=.9*spend:
   action=dict(id='risk-pause:'+str(c['id']),kind='pause_campaign',campaign_id=c['id'],status_before=9,nm_ids=sorted(members),risk_evidence=evidence)
   decision='Приостановить РК. Не пополнять.'
  elif st['status']==11 and c['balance']==0 and (not holds.get(str(c['id']))or holds.get(str(c['id']))=='Owner2Nov пока не пополнять'):
   targets={minima[str(c['id'])+':'+str(nm)]for nm in members}
   if len(targets)!=1:continue
   target=next(iter(targets));stable_contribution=sum(stable.get(nm,0)*member_models[nm][1]for nm in members);stress=sum(stable.get(nm,0)*member_models[nm][2]for nm in members)-spend
   # Never credit associated orders as incremental growth; retain their known downside
   # or charge an explicit two-logistics reserve when their own model is unavailable.
   for nm,v in order_models.items():
    if nm not in members:
     downside=min(0,v[1])*bynm[nm]if v is not None else -2*max(e[0]['logistics_cny']for e in member_models.values())*bynm[nm]
     stable_contribution+=downside;stress+=downside
   if stress<=0 or any(v[1]<=0 or v[0].get('buyout_fallback')for v in member_models.values())or not all(target<r['bids_kopecks'][zone]for r in st['nm_settings']):continue
   minimum=source['config']['minTopUp']/100;reserve=spend*3/len(closed);amount=max(minimum,math.ceil(max(0,reserve-c['balance'])/50)*50)
   evidence.update(modeled_after_ads_cny=stable_contribution-spend,stress_after_ads_cny=stress,expected_bids={str(n['nm_id']):n['bids_kopecks']for n in st['nm_settings']},member_inputs={str(nm):dict(price=v[0]['seller_price_cny'],cost=v[0]['own_cogs_rub'])for nm,v in member_models.items()})
   action=dict(id='recover:'+str(c['id']),kind='recover_campaign',campaign_id=c['id'],status_before=11,nm_ids=sorted(members),placement=zone,target_minor=target,amount_cny=amount,balance_before=c['balance'],recovery_evidence=evidence,supersedes_temporary_hold=holds.get(str(c['id'])))
   decision='Все '+str(len(members))+' ставок → '+str(target/100)+' CNY; пополнить на '+str(amount)+' CNY и возобновить.'
  if action:
   c['financial_recommendation']=decision;c['financial_action']=action;c['budget_action']=None;c['budget_short_note']='Решение по РК — в рекламном PNG.';c['budget_recommendation']='Без отдельного пополнения.'
   for r in c.get('focus',[]):r['action']=None
   row=dict(article=c['name'],decision=decision,action=action,nm=next(iter(members)),period=c.get('period'),financial_risk_review=True)
   c['focus']=[row];c['attention']=[row];audit.append(dict(campaign_id=c['id'],status='ready',evidence=evidence))
   for section in out.get('recommendation_directions',{}).values():section['rows']=[r for r in section.get('rows',[])if r.get('campaign_id')!=c['id']];section['count']=len(section['rows'])
 out['campaign_financial_review']=dict(revision='completed_risk_restart_v1',audit=audit,wb_writes=0,model_calls=0)
 return out
