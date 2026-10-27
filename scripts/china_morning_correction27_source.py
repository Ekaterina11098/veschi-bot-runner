"""One dated owner-requested read-only morning correction source; no Telegram calls."""
import copy,json,os
from datetime import datetime,timedelta
from china_advertising_state import AdvertisingIO
from china_advertising_v2 import http,build,stamp,MSK,daily_metrics,sums,ratio
from china_advertising_cards import enhance

DAY='2026-10-27';KEY='china_agent:morning_correction:'+DAY+':v1'
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or str(datetime.now(MSK).date())!=DAY:raise ValueError('Dated public main only')
 io=AdvertisingIO()
 if io.get(KEY):print('Source already collected; no repeated WB reads');return
 source=copy.deepcopy(io.get('china_agent:advertising_source:'+DAY+':v2'))
 if not source or source.get('cabinet')!='token_3':raise ValueError('Morning source unavailable')
 inventory=http(io,'/adv/v1/promotion/count')
 ids=sorted({x['advertId'] for g in inventory.get('adverts',[]) if g.get('status') in [4,9,11] for x in g.get('advert_list',[])})
 if not ids or len(ids)>50:raise ValueError('Unexpected campaign scope')
 campaigns=http(io,'/api/advert/v2/adverts?ids='+','.join(map(str,ids)))
 budgets=http(io,'/api/advert/v2/budget','POST',dict(advertIds=ids))
 stats=http(io,'/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate=2026-10-24&endDate='+DAY)
 config=http(io,'/api/advert/v1/config')
 if config.get('currency')!='CNY':raise ValueError('Currency mismatch')
 source.update(ids=ids,batches={'0':dict(campaigns=campaigns,budgets=budgets,stats=stats)},config=config,observed_at=stamp())
 query='telegram_api_cache?or=(cache_key.like.china_agent:ad_rule_execution:*,cache_key.like.china_agent:loss_ad_execution:*,cache_key.like.china_agent:codex_*:execution,cache_key.like.china_agent:owner_*:execution,cache_key.like.china_agent:price_execution:v1:*,cache_key.like.china_agent:new_ad_execution:*,cache_key.like.china_agent:hourly_cloud:execution:*,cache_key.like.china_agent:daily_ad_execution:v2:*)&updated_at=gte.2026-10-13&select=cache_key,payload&order=cache_key.asc&limit=100'
 source['executions']=[]
 for offset in range(0,2000,100):
  page=io.db(query+'&offset='+str(offset));source['executions']+=page
  if len(page)<100:break
 else:raise ValueError('History truncated')
 source['catalogue']=io.get('china_agent:prices:v1')
 rough=build(source);minimums={}
 for c in rough['campaigns']:
  ns=[r['nm'] for r in c['focus'] if not r.get('pending_first_day') and 'Выполнено.' not in r['decision']]
  if not ns or c['status']!=9 or c['payment']!='cpc':continue
  placement='search' if c['zone']=='поиск' else 'recommendation'
  result=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=c['id'],nm_ids=ns,payment_type='cpc',placement_types=[placement]))
  for nm in ns:
   values=[v['value'] for row in result.get('bids',[]) if row['nm_id']==nm for v in row['bids'] if v['type']==placement and v['currency']=='CNY']
   if len(values)!=1:raise ValueError('Missing minimum')
   minimums[str(c['id'])+':'+str(nm)]=values[0]
 bundle=enhance(build(source,minimums),source)
 clock=datetime.now(MSK);hours=clock.hour+clock.minute/60;until15=max(0,15-hours)
 byid={c['advertId']:c for c in stats};money={c['advertId']:c for c in budgets['adverts']};rows=[]
 for c in campaigns['adverts']:
  if c['status']!=9:continue
  cid=c['id'];raw=byid.get(cid);active={n['nm_id'] for n in c['nm_settings']};byday={};members={}
  if raw is None:rows.append(dict(campaign_id=cid,status='missing_stats'));continue
  for day in raw.get('days',[]):
   date=day['date'][:10];byday[date]=daily_metrics(day);values=[]
   for app in day.get('apps',[]):
    for n in app.get('nms',[]):
     if n['nmId'] in active:values.append(daily_metrics(n))
   members[date]=sums(values)
  zero=dict(spend=0,amount=0,orders=0,views=0,clicks=0)
  # Returned daily series omits inactive days, but an entirely missing response is unknown.
  today=byday.get(DAY,zero);current_today=members.get(DAY,zero);last=members.get('2026-10-26',zero)
  current_period=sums(members.get(d,zero) for d in ['2026-10-24','2026-10-25','2026-10-26'])
  balance=money[cid]['total']
  rate=max(current_today['spend']/max(hours,1),last['spend']/24,current_period['spend']/72)
  rows.append(dict(campaign_id=cid,name=c['settings']['name'],balance=balance,status='checked',observed_at=clock.isoformat(),today=today,current_today=current_today,current_last=last,current_period=current_period,remaining_members=len(active),current_drr_3days=ratio(current_period),current_drr_day=ratio(last),current_drr_today=ratio(current_today),rate_per_hour=rate,until15_need=rate*until15,risk_until15=balance<rate*until15,three_day_need=rate*72,minimum_topup=config['minTopUp']/100))
 payload=dict(status='collected',day=DAY,observed_at=clock.isoformat(),source=source,bundle=bundle,budget_rows=rows,wb_writes=0,telegram_calls=0,owner_request='Replace corrected morning advertising/budget PNGs and remove third attention PNG.')
 if not io.create(KEY,payload):raise ValueError('Concurrent collection')
 print(json.dumps(dict(status='collected',campaign_count=len(ids),wb_writes=0,telegram_calls=0)))
if __name__=='__main__':run()
