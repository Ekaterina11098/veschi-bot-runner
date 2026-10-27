"""Owner requested read-only growth proposal; no Telegram or marketplace write path."""
import os,json,copy,math,hashlib
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from china_cloud_cost_control import Cache,WB,validate_identity
from china_price_apply import IO
from china_bid_proposals import sources,candidates,daily,fresh_stock,io_config,timestamp
from china_advertising_plans import economics
from china_experience import assess_candidate
KEY='china_agent:owner_growth_plan:2026-10-27:v1'
MSK=ZoneInfo('Europe/Moscow')
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write:raise PermissionError('Proposal is read-only')
  return super().req(path,method,body,write=False)
class W:
 def __init__(self,c):self.c=c;self.now=datetime.now(timezone.utc);self.memo={}
 def get(self,k):
  if k not in self.memo:self.memo[k]=self.c.get(k)
  return copy.deepcopy(self.memo[k])
 def save(self,*a,**kw):raise PermissionError('Screening cannot change journals')
 def db(self,method,table,params=None,**kw):
  if method!='GET' or table!='telegram_api_cache':raise PermissionError('Cache read only')
  return self.c.req('GET',params)
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or datetime.now(MSK).date().isoformat()!='2026-10-27':raise ValueError('Dated public main only')
 c=Cache()
 if c.get(KEY):print('Already prepared; no repeat reads');return
 w=W(c);wb=ReadWB();io=IO();validate_identity(c,wb)
 view=sources(w);day=view['day'];last=w.now.astimezone(MSK).date()-timedelta(days=1)
 economy=w.get('china_agent:new_ad_source:v1:'+day) or {}
 if not timestamp(economy.get('observed_at')) or w.now-timestamp(economy['observed_at'])>timedelta(hours=24):raise ValueError('Dated own economics unavailable')
 changed_today={x['nm'] for x in view['changes'] if x.get('kind')=='bid' and timestamp(x.get('at')) and timestamp(x['at']).astimezone(MSK).date()==w.now.astimezone(MSK).date()}
 inv=wb.req('/adv/v1/promotion/count')
 ids=sorted({a['advertId'] for g in inv.get('adverts',[]) if g.get('status') in [9,11] for a in g.get('advert_list',[])})
 current={int(k):v for k,v in wb.campaigns(ids).items()};view['campaigns']=current
 rows,blocked=candidates(w,view,economy)
 raises=[r for r in rows if r['nm_id'] not in changed_today][:10]
 search={n['nm_id'] for camp in current.values() if camp['status']==9 and camp['settings']['placements'].get('search') for n in camp['nm_settings']}
 excluded={x['nm'] for x in view['changes'] if x.get('kind')=='excluded'}
 adds=[];add_block=[]
 for p in economy.get('products',[]):
  nm=int(p['nm_id'])
  if nm in search or nm in changed_today or nm in excluded or p.get('subject_id') not in [50,61]:continue
  try:
   ec=economics(economy,nm)
   if ec['finished']<5 or ec['available']<5 or not p.get('open_card_count') or p.get('funnel_orders_count',0)<5 or p.get('add_to_cart_count',0)<10:continue
   ch=[x for x in view['changes'] if x.get('nm')==nm and x.get('kind') in ['bid','added','price'] and timestamp(x.get('at'))]
   if any(timestamp(x['at']).astimezone(MSK).date()>=last for x in ch):continue
   if assess_candidate((economy.get('experience') or {}).get('experiences',[]),nm,dict(seller_price=ec['seller_price_cny'],stock_available=ec['available']))['needs_review']:continue
   targets=[camp for camp in current.values() if camp['status']==9 and camp.get('currency')=='CNY' and camp.get('bid_type')=='manual' and camp['settings'].get('placements')==dict(search=True,recommendations=False) and {n['subject']['id'] for n in camp['nm_settings']}=={p['subject_id']} and len(camp['nm_settings'])<50]
   if not targets:continue
   targets.sort(key=lambda camp:camp['id'])
   own=[]
   for camp in current.values():
    if camp['status']!=9 or not any(n['nm_id']==nm for n in camp['nm_settings']):continue
    if camp['settings']['placements'].get('search'):continue
    values=daily(view['stats'].get(camp['id']),nm)
    eligible=[str(last-timedelta(days=j)) for j in range(2,-1,-1)]
    cc=[timestamp(x['at']).astimezone(MSK).date() for x in ch if x.get('cid') in [None,camp['id']]]
    ds=[d for d in eligible if not cc or d>str(max(cc))]
    if not ds or any(d not in values for d in ds):continue
    v={k:sum(values[d][k] for d in ds) for k in ['spend','amount','orders','clicks']}
    if v['amount'] and v['orders']>=1 and v['spend']/v['amount']<=.04:own.append(dict(campaign_id=camp['id'],days=ds,**v))
   organic=dict(period_from=economy.get('period_from'),period_to=economy.get('period_to'),open_cards=p['open_card_count'],basket_events=p['add_to_cart_count'],funnel_orders=p['funnel_orders_count'],basis='all-source funnel, not search-specific or paid conversion')
   adds.append(dict(kind='ad_add_sku',campaign_id=targets[0]['id'],nm_id=nm,article=ec['article'],placement='search',old_minor=None,economics=ec,organic=organic,previous_ad=sorted(own,key=lambda x:-x['orders'])[:1],selection_orders=sum(x['orders'] for x in own),subject_id=p['subject_id']))
  except (ValueError,KeyError,TypeError) as ex:add_block.append(dict(nm_id=nm,reason=str(ex)))
 adds.sort(key=lambda r:(-r['selection_orders'],-r['organic']['funnel_orders'],-r['organic']['basket_events']))
 available={cid:50-len(camp['nm_settings']) for cid,camp in current.items()}
 selected_adds=[]
 for r in adds:
  if available[r['campaign_id']]<=0:continue
  selected_adds.append(r);available[r['campaign_id']]-=1
  if len(selected_adds)>=6:break
 selected=raises+selected_adds
 screen=dict(status='screened',observed_at=datetime.now(timezone.utc).isoformat(),raise_count=len(raises),add_count=len(selected_adds),excluded_today_ids=sorted(changed_today),blocked=blocked,add_candidates=len(adds),wb_writes=0,telegram_calls=0)
 c.create(KEY+':screen',screen)
 if not selected:
  c.create(KEY,dict(screen,status='blocked',items=[],reason='No eligible candidates after complete-day history and own economics screening'));return
 price_rows=io.wb('/api/v2/list/goods/filter?limit=1000&offset=0').get('listGoods',[])
 if len(price_rows)>=1000:raise ValueError('Price pagination incomplete')
 wanted={r['nm_id'] for r in selected};prices={str(p['nmID']):p for p in price_rows if p['nmID'] in wanted}
 stocks=fresh_stock(economy,[r['article'] for r in selected])
 refreshed=copy.deepcopy(economy)
 pm={p['nmID']:p for p in economy.get('prices',[])};pm.update({int(k):v for k,v in prices.items()});refreshed['prices']=list(pm.values())
 sm={s.get('article'):s for s in economy.get('stock',[])};sm.update({s['article']:s for s in stocks});refreshed['stock']=list(sm.values())
 selected_ids=sorted({r['campaign_id'] for r in raises})
 if selected_ids:
  stats=wb.req('/adv/v3/fullstats?ids='+','.join(map(str,selected_ids))+'&beginDate='+str(last-timedelta(days=2))+'&endDate='+str(last))
  view['stats'].update({r['advertId']:r for r in stats})
 validated,more_block=candidates(w,view,refreshed,[r['nm_id'] for r in raises]) if raises else ([],[])
 allowed={(r['campaign_id'],r['nm_id']):r for r in validated}
 cfg=io_config(io);step=cfg.get('cpcStep')
 if cfg.get('currency')!='CNY' or type(step)is not int or step<=0:raise ValueError('WB bid step unknown')
 mins={}
 for cid in sorted({r['campaign_id'] for r in selected}):
  for zone in ['search','recommendations']:
   ns=sorted({r['nm_id'] for r in selected if r['campaign_id']==cid and (r.get('placement') or 'search')==zone})
   if ns:
    try:mins.update({(cid,nm):v for nm,v in wb.minimums(cid,ns,zone).items()})
    except RuntimeError as ex:
     for nm in ns:more_block.append(dict(nm_id=nm,reason='Fresh minimum unavailable: '+str(ex)))
 items=[]
 prior_prices={p['nmID']:p['sizes'][0]['discountedPrice'] for p in economy['prices']}
 for r in selected:
  nm=r['nm_id'];cid=r['campaign_id']
  try:
   if nm in changed_today:raise ValueError('Already raised today')
   if nm not in {int(k) for k in prices} or sum((s.get('article') or '').casefold()==r['article'].casefold() for s in stocks)!=1:raise ValueError('Fresh price/stock/COGS missing')
   ec=economics(refreshed,nm)
   if ec['seller_price_cny']!=prior_prices.get(nm):raise ValueError('Price changed; need comparable full days')
   minimum=mins.get((cid,nm))
   if type(minimum)is not int:raise ValueError('Fresh minimum unavailable')
   if r in raises:
    if (cid,nm) not in allowed:raise ValueError('Fresh completed-day evidence invalid')
    rr=allowed[(cid,nm)];old=rr['current_minor'];target=int(math.floor(old*1.1/step+.5))*step
    if not old<target<=cfg['cpcMaxBid'] or target<minimum:raise ValueError('Rate step/minimum invalid')
    items.append(dict(kind='ad_raise_bid',campaign_id=cid,nm_id=nm,article=ec['article'],placement=rr['placement'],old_minor=old,target_minor=target,minimum_minor=minimum,economics=ec,evidence=rr,test_additional_cny=20))
   else:
    if nm in search or ec['available']<5:raise ValueError('Already search or insufficient stock')
    if minimum>cfg['cpcMaxBid']:raise ValueError('Minimum outside configuration')
    items.append(dict(r,target_minor=minimum,minimum_minor=minimum,economics=ec,test_additional_cny=20))
  except (ValueError,KeyError,TypeError) as ex:more_block.append(dict(nm_id=nm,reason=str(ex)))
 at=datetime.now(timezone.utc);digest=hashlib.sha256(json.dumps(items,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
 result=dict(status='pending_owner_approval' if items else 'blocked',items=items,plan_sha256=digest,created_at=at.isoformat(),expires_at=(at+timedelta(hours=2)).isoformat(),selection_completed_days_only=True,performance_current_day_used=False,excluded_today_ids=sorted(changed_today),blocked=blocked+more_block,screen=screen,config=cfg,current_campaigns={str(k):v for k,v in current.items()},wb_writes=0,telegram_calls=0,source_economics_observed_at=economy['observed_at'],assumptions='Preliminary own completed buyout/actual fees/historical delivery/current COGS; FX12 RUB/CNY, tax5%, handling10RUB assumptions; unknown common deductions not0. No guarantee DRR5% or position. Additional20CNY/item is a review threshold, not a WB cap. No automatic hourly control or funding.')
 if not c.create(KEY,result):raise ValueError('Concurrent plan preparation')
 print(json.dumps(dict(status=result['status'],items=len(items),raises=sum(i['kind']=='ad_raise_bid' for i in items),adds=sum(i['kind']=='ad_add_sku' for i in items),wb_writes=0,telegram_calls=0)))
if __name__=='__main__':main()
