"""Second pass: explicitly labelled small/low-traffic tests, without today's performance."""
import os,json,copy,math
from datetime import datetime,timezone,timedelta
from china_owner_remaining_review27 import W,ReadWB
from china_cloud_cost_control import Cache,validate_identity
from china_bid_proposals import sources,daily,fresh_stock,io_config,timestamp
from china_advertising_plans import economics
from china_price_apply import IO
KEY='china_agent:owner_remaining_review:2026-10-27:v2'
BASE='china_agent:owner_remaining_review:2026-10-27:v1'
def main():
 from zoneinfo import ZoneInfo
 MSK=ZoneInfo('Europe/Moscow')
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or str(datetime.now(MSK).date())!='2026-10-27':raise ValueError('Dated public main only')
 c=Cache()
 if c.get(KEY):print('Audit exists; no repeat reads');return
 base=c.get(BASE) or {}
 if base.get('status')!='checked':raise ValueError('All-campaign coverage not established')
 wb=ReadWB();validate_identity(c,wb);w=W(c);io=IO()
 result=dict(status='checking',created_at=w.now.isoformat(),wb_writes=0,telegram_calls=0,coverage_source=BASE)
 if not c.create(KEY,result):raise ValueError('Concurrent screening')
 try:
  view=sources(w);model=w.get('china_agent:new_ad_source:v1:2026-10-27') or {}
  shortlist=[r for r in base['blocked'] if r['reason'] in ['Малая завершённая выборка выкупа','Недостаточная собственная рекламная выборка']]
  ids=sorted({r['campaign_id'] for r in shortlist});current={int(k):v for k,v in wb.campaigns(ids).items()}
  last=w.now.astimezone(MSK).date()-timedelta(days=1);start=last-timedelta(days=2)
  raw=wb.req('/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate='+str(start)+'&endDate='+str(last));stats={s['advertId']:s for s in raw}
  binding=c.get('china_agent:daily_ad_message:v2:364') or {};pending=c.get('china_agent:loss_plan:v1:'+binding.get('plan_id','')) or {}
  pending_lower={i['nm_id'] for i in pending.get('items',[]) if not pending.get('invalidated_at') and i.get('kind') in ['ad_exclude_sku','ad_set_bid']}
  initial=[];blocked=[]
  for item in shortlist:
   cid=item['campaign_id'];nm=item['nm_id'];camp=current[cid]
   try:
    if nm in pending_lower:raise ValueError('Already has pending lower/exclude proposal')
    if camp['status']!=9:raise ValueError('Campaign inactive')
    member=next(n for n in camp['nm_settings'] if n['nm_id']==nm)
    changes=[x for x in view['changes'] if x.get('nm')==nm and x.get('kind') in ['bid','added','price','returned','relaunch'] and timestamp(x.get('at'))]
    if camp.get('timestamps',{}).get('started'):changes.append(dict(kind='added',at=camp['timestamps']['started']))
    latest=max(changes,key=lambda x:timestamp(x['at'])) if changes else None
    changed=timestamp(latest['at']).astimezone(MSK).date() if latest else None
    days=[str(start+timedelta(days=i)) for i in range(3) if changed is None or start+timedelta(days=i)>changed]
    if not days:raise ValueError('Full following day incomplete')
    values=daily(stats.get(cid),nm)
    if any(d not in values for d in days):raise ValueError('Incomplete full-day stats')
    p={k:sum(values[d][k] for d in days) for k in ['spend','amount','orders','clicks']}
    drr=p['spend']/p['amount']*100 if p['amount'] else None
    ec=economics(model,nm)
    paid_test=p['orders']>=1 and drr is not None and drr<=4
    traffic=p['orders']==0 and p['amount']==0 and p['clicks']<=20 and p['spend']<=min(5,.025*ec['seller_price_cny'])
    if not paid_test and not traffic:raise ValueError('Traffic spend/conversion does not justify higher bid')
    if ec['paid']<1 or ec['finished']<1:raise ValueError('Own positive buyout sample unavailable')
    if latest and latest['kind']=='bid' and latest.get('old',0)>latest.get('target',0) and len(days)<3:raise ValueError('Need3full days after reduction')
    zone='search' if camp['settings']['placements'].get('search') else 'recommendations'
    initial.append(dict(campaign_id=cid,nm_id=nm,article=ec['article'],placement=zone,old_minor=member['bids_kopecks'][zone],decision_days=days,evidence=p,drr=drr,traffic_test=traffic,small_sample=True,economics=ec))
   except (ValueError,KeyError,StopIteration) as error:blocked.append(dict(item,reason=str(error)))
  initial.sort(key=lambda r:(-r['evidence']['orders'],r['drr'] if r['drr'] is not None else 1000))
  unique=[];seen=set()
  for row in initial:
   if row['nm_id'] not in seen:unique.append(row);seen.add(row['nm_id'])
  checked=[]
  if unique:
   goods=io.wb('/api/v2/list/goods/filter?limit=1000&offset=0').get('listGoods',[])
   if len(goods)>=1000:raise ValueError('Price pagination incomplete')
   updated=copy.deepcopy(model);updated['prices']=goods;stock=fresh_stock(model,[r['article'] for r in unique]);updated['stock']=stock
   cfg=io_config(io);step=cfg.get('cpcStep')
   if cfg.get('currency')!='CNY' or type(step)is not int or step<=0:raise ValueError('Bid configuration ambiguous')
   for cid in sorted({r['campaign_id'] for r in unique}):
    for zone in ['search','recommendations']:
     rows=[r for r in unique if r['campaign_id']==cid and r['placement']==zone]
     if not rows:continue
     minima=wb.minimums(cid,[r['nm_id'] for r in rows],zone)
     for row in rows:
      try:
       ec=economics(updated,row['nm_id']);old=row['old_minor'];target=int(math.floor(old*1.1/step+.5))*step
       if ec['seller_price_cny']!=row['economics']['seller_price_cny']:raise ValueError('Price changed; wait for full comparable day')
       if not old<target<=cfg['cpcMaxBid'] or target<minima[row['nm_id']]:raise ValueError('WB minimum/step constraint')
       checked.append(dict(row,target_minor=target,minimum_minor=minima[row['nm_id']],economics=ec))
      except (ValueError,KeyError) as error:blocked.append(dict(row,reason=str(error)))
   result['fresh_stock']=stock
  result.update(status='checked',items=checked,blocked=blocked,observed_at=datetime.now(timezone.utc).isoformat(),expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),selection_completed_days_only=True,performance_today_used=False,policy='Small traffic tests with positive own preliminary economics; no proof of low DRR where zero orders, no fixed minimum3buyouts for owner-requested exploratory expansion',limitations='Own completed buyout sample may be1or2. Historical logistics/fees, FX12RUB/CNY tax5% handling10RUB assumptions. Not net profit, common deductions unknown. No marketplace changes or auto-funding.')
 except Exception as error:result.update(status='blocked',reason=str(error) if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__)
 c.put(KEY,result)
 print(json.dumps(dict(status=result['status'],items=len(result.get('items',[])),reason=result.get('reason'),wb_writes=0)))
if __name__=='__main__':main()
