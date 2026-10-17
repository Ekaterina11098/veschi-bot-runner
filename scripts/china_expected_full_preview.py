"""Owner preview: order-date expected profit using disclosed saved delivery model."""
import json,math
from decimal import Decimal
from china_agent.control_owner_preview import Preview
from china_agent.expected_order_profit import resolved_buyout_rate,expected_profit
from china_agent.price_experiment_result import experiment_result,zero_buyout_signal
from analytics.mpstats_primary import products
from datetime import datetime,timezone
class Full(Preview):
 def build_report(self):
  raw=self.get('china_agent:order_cohort_raw:2026-10-17') or {};rates=self.get('china_agent:expected_profit_rates:2026-10-17') or {}
  model=self.get('china_agent:expected_profit_delivery_model:v1') or {};prior=self.get('china_agent:control_owner_preview:2026-10-17') or {}
  if raw.get('status')!='acquired' or len(raw['products'])!=28:raise RuntimeError('28 complete order receipts required')
  rate_map={str(r['nm_id']):r for r in rates['rows']};prior_map={str(r['nm_id']):r for r in prior['products']}
  costs=self.db('GET','analytics_costs',params=dict(select='article,cost',limit=5000)) or []
  own={r['article'].casefold():r['cost'] for r in costs if r.get('article') and r.get('cost') is not None}
  read=lambda t,p:self.db('GET',t,params=p)
  periods={}
  for day in ('2026-10-14','2026-10-16'):
   rows,marker=products(read,'token_3',day,day,datetime.now(timezone.utc))
   if not marker:raise RuntimeError('Exact day receipt missing')
   periods[day]={str(r['nm_id']):r for r in rows}
  out=[];gaps=[]
  for product in raw['products']:
   nm=product['nm_id'];article=product['article'];obs=product['observation'];body=obs['data']
   if isinstance(body.get('data'),dict):body=body['data']
   rows=body['data']
   if body.get('total')!=len(rows) or len(rows)>=300:raise RuntimeError('Incomplete order pagination')
   rate=rate_map.get(nm);resolved=resolved_buyout_rate(rate.get('is_payed') if rate else None,rate.get('finished_orders') if rate else None,rate.get('is_payed_percent_after_returns') if rate else None)
   old=prior_map[nm];item={k:old.get(k) for k in ('article','nm_id','before_price','after_price','detected_at','assessment_date')}
   item.update(buyout_percent=resolved['percent'],buyout_basis=resolved['note'],buyout_sample=resolved['sample_size'],expected_profit_basis='order_date; MPStats forecast payout, own COGS, saved dispatch delivery and acceptance, exact day advertising; excludes unmodeled reverse-to-seller expenses')
   for label,day in (('before','2026-10-14'),('after','2026-10-16')):
    group=[];seen=set();cancelled=0
    for r in rows:
     if str(r.get('nm_id'))!=nm or r.get('api_id')!=10026946 or r.get('sa_name','').casefold()!=article.casefold():raise RuntimeError('Order identity mismatch')
     if str(r['order_dt'])[:10]!=day:continue
     identity=r.get('srid') or r.get('gnumber')
     if not identity or identity in seen:raise RuntimeError('Duplicate order')
     seen.add(identity)
     if r.get('is_canceled_order') not in (0,1,False,True):raise RuntimeError('Cancellation unknown')
     if r['is_canceled_order']:cancelled+=1;continue
     cost=own.get(article.casefold());delivery=(model.get('rows',{}).get(article) or {}).get('delivery_cny')
     if cost is None or delivery is None:raise RuntimeError('Known cost and model delivery required: '+article)
     net=Decimal(str(r['order_for_pay']));forward=Decimal(str(r['forward_logistic_rub']))
     # The source order payout includes its current forward logistics estimate.
     # Remove that amount once and use the same saved dispatch model for both cohorts.
     unshipped=net+forward
     retail=Decimal(str(r['retail_amount']));commission=Decimal(str(r['waitforcomission']))
     if abs(unshipped-(retail-commission))>Decimal('.06'):raise RuntimeError('Source forecast payout reconciliation failed: '+article)
     dispatch=Decimal(str(delivery))*Decimal(str(model['rub_per_cny']))+Decimal(str(model['acceptance_rub_per_dispatch']))
     group.append(dict(order_id=str(identity),buyout_profit=unshipped-Decimal(str(cost))-dispatch,nonbuyout_profit=-dispatch))
    daily=periods[day].get(nm)
    if daily is None:
     # Explicit card table is used only for its independently observed zero expenses.
     card=self.get('china_agent:control_gap_card:2026-10-17') or {}
     value=(card.get('data',{}).get('data',{}).get(day) or {})
     if article!='9-FurPanama-lblue' or card.get('status')!='received' or value.get('advertisement') is None:raise RuntimeError('Day advertising unavailable')
     ad=value['advertisement'];views=orders=None
    else:ad=daily['advertisement'];views=daily['open_card_count'];orders=daily['funnel_orders_count']
    calculated=expected_profit(group,resolved['probability'],ad,0)
    item[label]=dict(order_date=day,orders=len(group),cancelled=cancelled,expected_profit=calculated['expected_profit'],advertising=ad,views=views,funnel_orders=orders,conversion=orders/views if views else None)
   a,b=item['before'],item['after']
   item['result']=experiment_result(a['expected_profit'],b['expected_profit'],a['views'],a['funnel_orders'],b['views'],b['funnel_orders'],1,resolved['sample_size'])
   if rate:item['zero_buyout_signal']=zero_buyout_signal(rate['orders_count'],rate['is_payed'],rate['finished_orders'],rate['not_finished_orders'],rate['is_not_payed'],rate['finish_as_return'])
   out.append(item)
  result=dict(status='complete_disclosed_forecast_model',products=out,rate_period=[rates['period_from'],rates['period_to']],rate_observed_at=rates['observed_at'],delivery_model_source='VESCHI_China_prices_recalculated_2026-10-03.xlsx',limitations=['Delivery is saved model, not newly verified tariff.','Additional reverse-to-seller costs are excluded as in saved pricing model.','Source order payout forecast is not settled cash.','One full day, no causal success claim.','9-FurPanama-lblue has no returned funnel history.'],telegram_calls=0,wb_writes=0)
  self.save('china_agent:expected_full_owner_preview:2026-10-17',result)
  print(json.dumps(dict(status=result['status'],products=len(out),telegram_calls=0,wb_writes=0)))
if __name__=='__main__':
 w=Full('control')
 try:w.build_report()
 finally:
  import requests
  requests.sessions.Session.request=w.original_http
