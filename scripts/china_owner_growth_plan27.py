"""Finalize owner-requested proposal using explicitly confirmed uniform category rates."""
import os,copy,json,hashlib
from datetime import datetime,timezone,timedelta
from china_cloud_cost_control import Cache,WB,validate_identity
from china_price_apply import IO
from china_bid_proposals import fresh_stock
from china_advertising_plans import economics
OLD='china_agent:owner_growth_plan:2026-10-27:v1'
KEY='china_agent:owner_growth_plan:2026-10-27:v2'
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 c=Cache()
 if c.get(KEY):return
 p=c.get(OLD);source=c.get('china_agent:new_ad_source:v1:2026-10-27')
 if not p or p.get('status')!='pending_owner_approval':raise ValueError('Prior screening missing')
 wb=WB();validate_identity(c,wb);io=IO()
 wanted={1473243891,1473243896,1473243901,1473243905,1473244342,1556488181}
 products={int(x['nm_id']):x for x in source['products']}
 prices=io.wb('/api/v2/list/goods/filter?limit=1000&offset=0').get('listGoods',[])
 if len(prices)>=1000:raise ValueError('Prices incomplete')
 stock=fresh_stock(source,[products[n]['sa_name'] for n in wanted])
 source=copy.deepcopy(source);source['prices']=prices;sm={s.get('article'):s for s in source['stock']};sm.update({s['article']:s for s in stock});source['stock']=list(sm.values())
 current={int(k):v for k,v in wb.campaigns([int(cid) for cid in p['current_campaigns']]).items()}
 search={n['nm_id'] for camp in current.values() if camp['status']==9 and camp['settings']['placements'].get('search') for n in camp['nm_settings']}
 prior_prices={x['nmID']:x['sizes'][0]['discountedPrice'] for x in (c.get('china_agent:new_ad_source:v1:2026-10-27') or {})['prices']}
 items=list(p['items']);blocked=[]
 for nm in sorted(wanted):
  try:
   if nm in search or nm in p['excluded_today_ids']:raise ValueError('Already in search or raised today')
   r=products[nm];ec=economics(source,nm)
   if ec['seller_price_cny']!=prior_prices[nm] or ec['available']<5:raise ValueError('Price changed or insufficient stock')
   if sum((s.get('article') or '').casefold()==ec['article'].casefold() for s in stock)!=1:raise ValueError('Fresh stock missing')
   category=r['subject_id']
   if category not in [50,61]:raise ValueError('Owner category rate unavailable')
   cid=41298169 if category==50 else 41325637
   camp=current[cid]
   if camp['status']!=9 or len(camp['nm_settings'])+sum(i.get('kind')=='ad_add_sku' and i['campaign_id']==cid for i in items)>=50:raise ValueError('Target scope/capacity changed')
   if {n['subject']['id'] for n in camp['nm_settings']}!={category}:raise ValueError('Category mismatch')
   target=28 if category==50 else 23
   items.append(dict(kind='ad_add_sku',campaign_id=cid,nm_id=nm,article=ec['article'],placement='search',old_minor=None,target_minor=target,category_rate_minor=target,category_rate_source='Owner explicit Codex27Oct: ставки у тебя есть: они одинаковые для всех товаров категории; bag0.28/umbrella0.23 known verified current categories',minimum_individual_before_add_unavailable=True,economics=ec,organic=dict(open_cards=r['open_card_count'],basket_events=r['add_to_cart_count'],funnel_orders=r['funnel_orders_count'],basis='All-source prior completed30day funnel, not search-specific conversion'),test_additional_cny=20))
  except (ValueError,KeyError,TypeError) as ex:blocked.append(dict(nm_id=nm,reason=str(ex)))
 at=datetime.now(timezone.utc);result=dict(status='pending_owner_approval',plan_id='codex-growth-27oct-1438',items=items,plan_sha256=hashlib.sha256(json.dumps(items,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),created_at=at.isoformat(),expires_at=(at+timedelta(hours=2)).isoformat(),selection_completed_days_only=True,performance_current_day_used=False,excluded_today_ids=p['excluded_today_ids'],source_plan=OLD,blocked=blocked,current_campaigns={str(k):v for k,v in current.items()},fresh_prices=[x for x in prices if x['nmID'] in wanted],fresh_stock=stock,wb_writes=0,telegram_calls=0,assumptions=p['assumptions'],owner_uniform_category_rate_confirmed=True)
 if not c.create(KEY,result):raise ValueError('Concurrent plan')
 print(json.dumps(dict(items=len(items),raises=sum(i['kind']=='ad_raise_bid' for i in items),adds=sum(i['kind']=='ad_add_sku' for i in items),wb_writes=0,telegram_calls=0)))
if __name__=='__main__':main()
