"""Dated owner request: audit ALL other active CPC campaigns, no WB or Telegram writes."""
import os,json,copy,math
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from china_cloud_cost_control import Cache,WB,validate_identity
from china_bid_proposals import sources,candidates,fresh_stock,io_config,timestamp
from china_price_apply import IO
from china_advertising_plans import economics
KEY='china_agent:owner_remaining_review:2026-10-27:v1'
EXCLUDED={41155824,41270474,41296359,41296363}
MSK=ZoneInfo('Europe/Moscow')
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write:raise PermissionError('Review has no WB write path')
  return super().req(path,method,body,write=False)
class W:
 def __init__(self,c):self.c=c;self.now=datetime.now(timezone.utc);self.memo={}
 def get(self,k):
  if k not in self.memo:self.memo[k]=self.c.get(k)
  return copy.deepcopy(self.memo[k])
 def db(self,method,table,params=None,**kw):
  if method!='GET' or table!='telegram_api_cache':raise ValueError('Cache read only')
  return self.c.req('GET',params)
 def save(self,*a,**kw):raise PermissionError('No dialog or marketplace writes')
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or str(datetime.now(MSK).date())!='2026-10-27':raise ValueError('Dated public main only')
 c=Cache()
 if c.get(KEY):print('Existing audit; no repeated polling');return
 wb=ReadWB();validate_identity(c,wb);w=W(c);io=IO()
 result=dict(status='checking',created_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_calls=0,excluded_previously_reviewed_campaigns=sorted(EXCLUDED))
 if not c.create(KEY,result):raise ValueError('Concurrent audit')
 try:
  view=sources(w);model=w.get('china_agent:new_ad_source:v1:2026-10-27') or {}
  if not timestamp(model.get('observed_at')) or w.now-timestamp(model['observed_at'])>timedelta(hours=24):raise ValueError('Dated economics stale')
  inv=wb.req('/adv/v1/promotion/count')
  active=sorted({r['advertId'] for g in inv.get('adverts',[]) if g.get('status')==9 for r in g.get('advert_list',[])})
  current={}
  for pos in range(0,len(active),50):current.update({int(k):v for k,v in wb.campaigns(active[pos:pos+50]).items()})
  remaining={cid:v for cid,v in current.items() if cid not in EXCLUDED}
  result['active_count']=len(active);result['remaining_count']=len(remaining);result['campaigns']=remaining
  last=w.now.astimezone(MSK).date()-timedelta(days=1);start=last-timedelta(days=2)
  ids=sorted(remaining);stats=[]
  for pos in range(0,len(ids),50):stats+=wb.req('/adv/v3/fullstats?ids='+','.join(map(str,ids[pos:pos+50]))+'&beginDate='+str(start)+'&endDate='+str(last))
  # Never let today's counters overwrite completed-day evidence.
  view['stats']={r['advertId']:r for r in stats};view['campaigns']=remaining
  history=list(view['changes'])
  for camp in remaining.values():
   started=camp.get('timestamps',{}).get('started')
   if started:
    for member in camp.get('nm_settings',[]):history.append(dict(cid=camp['id'],nm=member['nm_id'],kind='added',at=started))
  view['changes']=history;result['selection_from']=str(start);result['selection_to']=str(last)
  rows=[];blocked=[];summaries=[]
  for cid,camp in remaining.items():
   eligible=[];memberblock=[]
   for member in camp.get('nm_settings',[]):
    nm=member['nm_id'];changes=[x for x in history if x.get('nm')==nm and x.get('kind') in ['bid','added','price','returned','relaunch'] and timestamp(x.get('at'))]
    latest=max(changes,key=lambda x:timestamp(x['at'])) if changes else None
    if latest and timestamp(latest['at']).astimezone(MSK).date()>=last:
     memberblock.append(dict(campaign_id=cid,nm_id=nm,reason='Full following MSK day not completed after latest SKU change/launch',latest_change=latest));continue
    eligible.append(member)
   scoped=dict(view,campaigns={cid:dict(camp,nm_settings=eligible)})
   found,rejected=candidates(w,scoped,model) if eligible else ([],[])
   rejected=[dict(r,campaign_id=cid) for r in rejected]+memberblock
   rows+=found;blocked+=rejected
   raw=view['stats'].get(cid)
   summaries.append(dict(campaign_id=cid,name=camp['settings']['name'],placement='search' if camp['settings']['placements'].get('search') else 'recommendations',member_count=len(camp.get('nm_settings',[])),eligible_after_change_guard=len(eligible),initial_candidates=len(found),blocked=len(rejected),stats_available=raw is not None,spend=raw.get('sum') if raw else None,amount=raw.get('sum_price') if raw else None,orders=raw.get('orders') if raw else None,clicks=raw.get('clicks') if raw else None))
  rows.sort(key=lambda r:(-r['previous_full_days']['orders'],r['previous_drr'] if r['previous_drr'] is not None else 1000))
  selected=[];seen=set()
  for row in rows:
   if row['nm_id'] not in seen:selected.append(row);seen.add(row['nm_id'])
  result.update(summaries=summaries,screened_candidate_count=len(selected),blocked=blocked)
  checked=[]
  if selected:
   wanted={r['nm_id'] for r in selected}
   # Refresh actual seller prices and MSK stock/COGS only for screened candidates.
   prices={}
   for nm in sorted(wanted):
    goods=io.wb('/api/v2/list/goods/filter?limit=1000&offset=0&filterNmID='+str(nm)).get('listGoods',[])
    if len(goods)!=1 or goods[0]['nmID']!=nm:raise ValueError('Exact candidate price unavailable')
    prices[nm]=goods[0]
   stock=fresh_stock(model,[r['article'] for r in selected])
   updated=copy.deepcopy(model)
   updated['prices']=list({p['nmID']:p for p in model.get('prices',[])}|prices).values() if False else list(({p['nmID']:p for p in model.get('prices',[])}|prices).values())
   sm={s['article'].casefold():s for s in model.get('stock',[])};sm.update({s['article'].casefold():s for s in stock});updated['stock']=list(sm.values())
   cfg=io_config(io);step=cfg.get('cpcStep')
   if cfg.get('currency')!='CNY' or type(step)is not int or step<=0:raise ValueError('Unknown CNY bid step')
   for cid in sorted({r['campaign_id'] for r in selected}):
    for zone in ['search','recommendations']:
     rs=[r for r in selected if r['campaign_id']==cid and r['placement']==zone]
     if not rs:continue
     minima=wb.minimums(cid,[r['nm_id'] for r in rs],zone)
     for row in rs:
      try:
       nm=row['nm_id'];old=row['current_minor'];target=int(math.floor(old*1.1/step+.5))*step
       ec=economics(updated,nm)
       if prices[nm].get('vendorCode')!=row['article'] or ec['seller_price_cny']!=row['economics']['seller_price_cny']:raise ValueError('Seller price changed; need comparable complete day')
       if not old<target<=cfg['cpcMaxBid'] or target<minima[nm]:raise ValueError('Target outside WB constraints')
       checked.append(dict(row,old_minor=old,target_minor=target,minimum_minor=minima[nm],economics=ec))
      except (ValueError,KeyError,TypeError) as error:blocked.append(dict(campaign_id=cid,nm_id=row['nm_id'],article=row['article'],reason=str(error)))
   result['fresh_stock']=stock;result['fresh_prices']=prices
  result.update(status='checked',items=checked,blocked=blocked,observed_at=datetime.now(timezone.utc).isoformat(),expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),performance_today_used=False,selection_rule='Completed days24-26 only, exclude day of latest global SKU change and require next full MSK day, no same-day repeats; own positive preliminary economics required, low-traffic tests explicitly labelled',limitations='FX12RUB/CNY,tax5%,handling10RUB; historical own buyout/fees/logistics. Unknown common deductions not0; preliminary forecast not netprofit, no guarantee DRR5%. No actions executed.')
 except Exception as error:result.update(status='blocked',reason=str(error) if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__,completed_at=datetime.now(timezone.utc).isoformat())
 c.put(KEY,result)
 print(json.dumps({k:result.get(k) for k in ['status','active_count','remaining_count','screened_candidate_count','observed_at','reason','wb_writes']}))
if __name__=='__main__':main()
