"""Carry calculated completed-day recommendations into the current-day report."""
import copy
from datetime import date,timedelta,datetime,timezone
from china_advertising_v2 import collect,refresh_budget_context,build,http,save,history,MSK,never_started_draft
def include_closed(io,source,day):
 source=copy.deepcopy(source)
 inventory=http(io,'/adv/v1/promotion/count')
 ids=sorted({a['advertId']for g in inventory.get('adverts',[])if g['status']==7 for a in g.get('advert_list',[])}-set(source['ids']))
 if len(ids)>50:raise ValueError('Closed campaign scope requires bounded pagination')
 if ids:
  joined=','.join(map(str,ids));source['ids']=sorted(source['ids']+ids)
  source['batches']['closed']=dict(campaigns=http(io,'/api/advert/v2/adverts?ids='+joined),budgets=http(io,'/api/advert/v2/budget','POST',dict(advertIds=ids)),stats=http(io,'/adv/v3/fullstats?ids='+joined+'&beginDate='+day+'&endDate='+day))
 key='china_agent:advertising_midday_inclusive:'+day+':v1';save(io,key,source)
 return source
def merge_completed(bundle,review,source_ref):
 out=copy.deepcopy(bundle);closed={c['id']:c for c in review['campaigns']}
 for c in out['campaigns']:
  c['attention']=[];r=closed.get(c['id'])
  if not r:continue
  done=[]
  for row in r.get('focus',[]):
   if row.get('already_excluded') or row.get('pending_first_day'):
    if row.get('done')and row.get('done')!='Нет подтверждённых изменений':done.append(row['article']+': '+row['done'])
    continue
   if not row.get('action'):continue
   days=(row.get('comparison')or{}).get('to_days')or review['days']
   if not days or days[-1]>=out['day']:raise ValueError('Partial day cannot become an action basis')
   m=(row.get('comparison')or{}).get('after')or row['period']
   c['attention'].append(dict(article=row['article'],decision=row['decision'],action=row['action'],spend=m['spend'],clicks=m['clicks'],closed_day_evidence=dict(period_from=days[0],period_to=days[-1],verified=True,source_ref=source_ref,postclick_reviewed=True,metrics=m)))
  c['completed_actions']=list(dict.fromkeys(done))
 out['recommendation_basis']='completed_days_with_fresh_economics_and_current_state'
 return out
def attach(io,bundle,day):
 from china_morning_readiness import enrich_economics
 from china_advertising_cards import enhance
 from china_advertising_economic_review import apply
 current=io.get('china_agent:advertising_midday_inclusive:'+day+':v1')or collect(io,day,current=True);source=copy.deepcopy(collect(io,day))
 end=str(date.fromisoformat(day)-timedelta(days=1))
 if source.get('day_quality',{}).get('usable')is not True or source['period_to']!=end:raise ValueError('Usable completed-day source required')
 source=refresh_budget_context(io,source,day)
 saved_stats={r['advertId']:copy.deepcopy(r) for b in source['batches'].values() for r in b['stats']}
 source['ids']=list(current['ids']);source['batches']=copy.deepcopy(current['batches'])
 for batch in source['batches'].values():
  ids=[c['id']for c in batch['campaigns']['adverts'] if not never_started_draft(c)]
  missing=[cid for cid in ids if cid not in saved_stats]
  if missing:
   extra=http(io,'/adv/v3/fullstats?ids='+','.join(map(str,missing))+'&beginDate='+source['period_from']+'&endDate='+end)
   saved_stats.update({r['advertId']:r for r in extra})
  if any(cid not in saved_stats for cid in ids):raise ValueError('Completed-day campaign history incomplete')
  batch['stats']=[copy.deepcopy(saved_stats[cid]) for cid in ids]
 source['observed_at']=datetime.now(timezone.utc).isoformat();source['budget_balance_observed_at_iso']=current.get('completed_at',current['observed_at'])
 rough=build(source);source=enrich_economics(io,source,rough,day)
 if source.get('morning_fresh_inputs',{}).get('errors'):raise ValueError('Fresh completed-day recommendation inputs incomplete')
 minima={}
 for c in rough['campaigns']:
  # Economics may create a precise action from a formerly unready row.
  ids=[r['nm']for r in c['focus']if not r.get('pending_first_day')and 'Выполнено.'not in r['decision']]
  if not ids or c['status']!=9 or c['payment']!='cpc':continue
  zone='search'if c['zone']=='поиск'else'recommendation'
  raw=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=c['id'],nm_ids=ids,payment_type='cpc',placement_types=[zone]))
  found=set()
  for row in raw.get('bids',[]):
   values=[v['value']for v in row['bids']if v['type']==zone and v['currency']=='CNY']
   if len(values)!=1:raise ValueError('Unverified current minimum')
   found.add(row['nm_id']);minima[str(c['id'])+':'+str(row['nm_id'])]=values[0]
  if found!=set(ids):raise ValueError('Incomplete current minima')
 review=apply(enhance(build(source,minima),source),source,minima)
 if not review.get('economic_review_complete'):raise ValueError('Incomplete economic review; do not freeze empty recommendations')
 key='china_agent:advertising_midday_completed:'+day+':v1';save(io,key,dict(source=source,review=review,status='complete',observed_at=source['observed_at'],wb_writes=0))
 return merge_completed(bundle,review,key)

