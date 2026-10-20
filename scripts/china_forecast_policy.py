"""Resolve current per-article settled buyout before initial-price forecasts."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from analytics.mpstats_primary import products
from .core import forecast_price
def forecast_for_product(data,arguments):
 now=datetime.now(ZoneInfo('Europe/Moscow'));end=now.date()-timedelta(days=1);start=end-timedelta(days=29)
 rows,marker=products(data.read,'token_3',start,end,now)
 if not marker:raise ValueError('Current completed-order buyout source unavailable')
 query=str(arguments.get('article','')).casefold()
 matches=[r for r in rows if r['sa_name'].casefold()==query or str(r['nm_id'])==query or r['sa_name'].split('-')[0].casefold()==query]
 if len(matches)!=1:raise ValueError('Exact China article required for its own buyout rate')
 row=matches[0]
 costs=data.read('analytics_costs',{'article':'eq.'+row['sa_name'],'select':'cost','limit':2}) or []
 if len(costs)!=1:raise ValueError('Own cost unavailable')
 saved=data.read('telegram_api_cache',{'cache_key':'eq.china_agent:expected_profit_delivery_model:v1','select':'payload','limit':1}) or []
 if len(saved)!=1 or saved[0]['payload'].get('cabinet')!='token_3':raise ValueError('China delivery model unavailable')
 model=saved[0]['payload'];delivery=(model.get('rows',{}).get(row['sa_name']) or {}).get('delivery_cny')
 if delivery is None:raise ValueError('Agreed product delivery unavailable')
 result=forecast_price(costs[0]['cost'],delivery*model['rub_per_cny'],buyout_stats=row)
 result.update(article=row['sa_name'],nm_id=row['nm_id'],buyout_period_from=str(start),buyout_period_to=str(end),source_snapshot_id=marker['id'])
 return result
