"""Read existing shared advertising evidence before collecting again."""
from datetime import timedelta
from china_advertising_v2 import MSK
def shared(w,first,last,ids):
 day=str(w.now.astimezone(MSK).date());base=w.get('china_agent:advertising_source:'+day+':v2')
 if not base or base.get('status')!='complete' or str(first)<base['period_from']:return None
 current=w.get('china_agent:advertising_intraday:'+day+':v1')
 if not current:
  previous=str(w.now.astimezone(MSK).date()-timedelta(days=1))
  current=w.get('china_agent:owner_profit_compare:'+previous+':'+day+':v1')
 raw={};campaigns=[]
 for b in base['batches'].values():
  campaigns+=b['campaigns'].get('adverts',[])
  for c in b['stats']:raw[c['advertId']]={d['date'][:10]:d for d in c['days']}
 end=base['period_to'];observed=base['observed_at']
 if current:
  for b in current['ad_batches']:
   for c in b['data']:raw.setdefault(c['advertId'],{}).update({d['date'][:10]:d for d in c['days']})
  end=day;observed=current['observed_at']
 if str(last)>end:return None
 selected=[];totals={};campaign_daily={}
 for cid,ds in raw.items():
  campaign_daily[str(cid)]={}
  for d,v in sorted(ds.items()):
   if not str(first)<=d<=str(last):continue
   row=dict(campaign_id=cid,date=d,level='campaign_total',**{k:v.get(k) for k in ['sum','sum_price','orders','clicks','views']})
   campaign_daily[str(cid)][d]={k:v.get(k) for k in ['sum','sum_price','orders','clicks','views']}
   t=totals.setdefault(d,dict(spend_cny=0,ad_order_amount_cny=0,ad_orders_attributed=0))
   t['spend_cny']+=v['sum'];t['ad_order_amount_cny']+=v['sum_price'];t['ad_orders_attributed']+=v['orders']
   if not ids:selected.append(row)
   for a in v['apps']:
    for n in a['nms']:
     if not ids or n['nmId'] in ids:selected.append(dict(campaign_id=cid,date=d,nm_id=n['nmId'],level='SKU_app',**{k:n.get(k) for k in ['sum','sum_price','orders','clicks','views']}))
 for t in totals.values():t['drr_pct']=100*t['spend_cny']/t['ad_order_amount_cny'] if t['ad_order_amount_cny'] else None
 return dict(source='shared WB advertising snapshots',cabinet='token_3',observed_at=observed,period_from=str(first),period_to=str(last),cached=True,wb_reads=0,wb_writes=0,rows=selected,campaign_daily=campaign_daily,totals_by_day=totals,campaigns=[dict(id=c['id'],status=c['status'],settings=c['settings'],sku_count=len(c['nm_settings']),membership_observed_at=base['observed_at']) for c in campaigns],note='Показатели из сохранённых датированных срезов; сегодняшний день неполный. Итоги РК не складывать с SKU_app. Рекламная атрибуция не уникальные заказы WB. Проверенные последующие исключения смотреть в read_recent_actions.')
