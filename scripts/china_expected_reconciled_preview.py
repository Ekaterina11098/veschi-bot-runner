"""Reconcile order-date forecast to WB orders; all monetary terms are disclosed scenarios."""
from datetime import datetime,timezone
from decimal import Decimal
import json
from china_agent.control_owner_preview import Preview
from china_agent.expected_order_profit import resolved_buyout_rate,expected_profit
from china_agent.price_experiment_result import experiment_result
from analytics.mpstats_primary import products
class Reconciled(Preview):
 def build(self):
  prior=self.get('china_agent:expected_full_owner_preview:2026-10-17') or {}
  model=self.get('china_agent:expected_profit_delivery_model:v1') or {}
  read=lambda t,p:self.db('GET',t,params=p)
  rows,marker=products(read,'token_3','2026-09-17','2026-10-16',datetime.now(timezone.utc))
  if not marker:raise RuntimeError('Buyout/cost parameter source missing')
  source={str(r['nm_id']):r for r in rows}
  own={r['article'].casefold():r['cost'] for r in read('analytics_costs',dict(select='article,cost',limit=5000)) or [] if r.get('article') and r.get('cost') is not None}
  wb={}
  for day in ('2026-10-14','2026-10-16'):
   receipt=self.get('china_agent:wb_order_gaps:day:'+day) or {}
   if (receipt.get('cabinet')!='token_3' or receipt.get('status')!='complete' or receipt.get('seller_identity_verified') is not True or receipt.get('date')!=day):raise RuntimeError('Verified WB day missing')
   unique={}
   for r in receipt['rows']:
    if str(r['date'])[:10]!=day or not r.get('srid') or type(r.get('isCancel')) is not bool:raise RuntimeError('WB order identity/date missing')
    identity=r['srid']
    if identity in unique and str(unique[identity]['nmId'])!=str(r['nmId']):raise RuntimeError('WB order identity conflict')
    if identity not in unique or str(r.get('lastChangeDate',''))>=str(unique[identity].get('lastChangeDate','')):unique[identity]=r
   wb[day]=dict(rows=list(unique.values()),observed_at=receipt['observed_at'])
  out=[]
  for old in prior['products']:
   nm=old['nm_id'];article=old['article'];params=source.get(nm)
   item=dict(old)
   # Same estimated fee conditions before/after, so current fee mix is not itself
   # mistaken for an effect of the price experiment. This is not settled cash.
   retention=None;fee_basis=None
   if params:
    gross=Decimal(str(params['sales_ret_sum']));commission=Decimal(str(params['total_commission_without_spp']));acq=Decimal(str(params['acquiring']))
    if gross>0:
     retention=1-(commission+acq)/gross;fee_basis='Observed 30-day own-SKU commission/acquiring including SPP compensation, held constant across comparison'
    else:
     retention=1-Decimal(str(params['default_comission']))/100;fee_basis='MPStats default own-SKU commission scenario; acquiring observed zero in period'
   for label,day,pricefield in (('before','2026-10-14','before_price'),('after','2026-10-16','after_price')):
    orders=[r for r in wb[day]['rows'] if str(r['nmId'])==nm and not r['isCancel']]
    group=[]
    if orders:
     cost=own.get(article.casefold());delivery=(model['rows'].get(article) or {}).get('delivery_cny')
     if cost is None or delivery is None or retention is None:raise RuntimeError('Forecast scenario terms missing')
     dispatch=Decimal(str(delivery))*Decimal(str(model['rub_per_cny']))+Decimal(str(model['acceptance_rub_per_dispatch']))
     price=Decimal(str(item[pricefield]))*Decimal(str(model['rub_per_cny']))
     for r in orders:group.append(dict(order_id=r['srid'],buyout_profit=price*retention-Decimal(str(cost))-dispatch,nonbuyout_profit=-dispatch))
    p=Decimal(str(item['buyout_percent']))/100
    calculated=expected_profit(group,p,item[label]['advertising'],0)
    item[label]=dict(item[label],orders=len(orders),expected_profit=calculated['expected_profit'],wb_observed_at=wb[day]['observed_at'])
   a,b=item['before'],item['after']
   item['result']=experiment_result(a['expected_profit'],b['expected_profit'],a['views'],a['funnel_orders'],b['views'],b['funnel_orders'],1,item['buyout_sample'])
   if a['orders']==b['orders']==0:
    item['result'].update(status='no_orders',result_action='Заказов в обоих периодах нет; изменение результата связано с рекламными расходами. Влияние цены не оценено.')
   if item.get('zero_buyout_signal',{}).get('attention'):
    item['result'].update(status='zero_buyout_attention',result_action='Заказы есть, подтверждённых выкупов нет — проверить причины невыкупа товара отдельно от изменения цены.')
   item.update(fee_basis=fee_basis,retained_revenue_factor=float(retention) if retention is not None else None)
   out.append(item)
  result=dict(prior,status='reconciled_disclosed_forecast_model',products=out,order_sources={d:v['observed_at'] for d,v in wb.items()},forecast_price_basis='Observed seller prices before/after valued at agreed 12 RUB/CNY; not per-order price confirmation',forecast_fee_basis='Same observed own-SKU 30-day effective fee mix or reported own-SKU default tariff before/after; a scenario, not confirmed future tariff',limitations=['Forecast scenario, not actual profit.','Historical delivery model of 03 October, acceptance 10 RUB, 12 RUB/CNY.','Additional reverse-to-seller costs and unallocated charges not included.','Order counts WB, funnel conversion MPStats: counters have different definitions.','One full day, preliminary only.','9-FurPanama-lblue funnel history unavailable.'])
  self.save('china_agent:expected_reconciled_owner_preview:2026-10-17',result)
  print(json.dumps(dict(status=result['status'],products=len(out),telegram_calls=0,wb_writes=0)))
if __name__=='__main__':
 w=Reconciled('control')
 try:w.build()
 finally:
  import requests
  requests.sessions.Session.request=w.original_http
