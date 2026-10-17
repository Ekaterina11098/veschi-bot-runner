"""Current per-SKU settled buyout sample for expected China order profits."""
import json
from datetime import datetime,timezone
from china_agent.control_owner_preview import Preview
from analytics.mpstats_primary import products
class Rates(Preview):
 def collect_rates(self):
  start='2026-09-17';end='2026-10-16'
  self.acquire({(start,end)})
  read=lambda t,p:self.db('GET',t,params=p)
  rows,marker=products(read,'token_3',start,end,datetime.now(timezone.utc))
  if not marker:raise RuntimeError('Current buyout sample unavailable')
  cohort=self.get('china_agent:order_cohort_raw:2026-10-17') or {}
  wanted={p['nm_id'] for p in cohort.get('products',[])}
  result=[]
  for r in rows:
   if str(r['nm_id']) not in wanted:continue
   result.append({k:r.get(k) for k in ('nm_id','p_id','sa_name','orders_count','finished_orders','not_finished_orders','is_payed','is_not_payed','finish_as_return','is_payed_percent','is_payed_percent_after_returns','average_delivery_cost','default_logistic','forwardlogisticsum','backwardlogisticsum','sales_count','returns_count','advertisement','default_comission','acquiring','sales_sum_without_spp')})
  self.save('china_agent:expected_profit_rates:2026-10-17',dict(cabinet='token_3',period_from=start,period_to=end,snapshot_id=marker['id'],observed_at=marker['collected_at'],rows=result,telegram_calls=0,wb_writes=0))
  print(json.dumps(dict(products=len(result),source_snapshot_id=marker['id'],telegram_calls=0,wb_writes=0)))
if __name__=='__main__':
 w=Rates('control')
 try:w.collect_rates()
 finally:
  import requests
  requests.sessions.Session.request=w.original_http
