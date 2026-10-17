"""Recalculate private preview from exact order identities; never deliver."""
import json,os
from china_agent.control_owner_preview import Preview
from china_agent.order_cohort_math import cohort
class Calculate(Preview):
 def calculate(self):
  raw=self.get('china_agent:order_cohort_raw:2026-10-17') or {}
  if raw.get('status')!='acquired' or len(raw.get('products',[]))!=28:raise RuntimeError('All 28 order receipts required')
  costs=self.db('GET','analytics_costs',params=dict(select='article,cost',limit=5000)) or []
  own={r['article'].casefold():r['cost'] for r in costs if r.get('article') and r.get('cost') is not None}
  out=[]
  for p in raw['products']:
   obs=p['observation'];body=obs['data']
   if isinstance(body.get('data'),dict):body=body['data']
   rows=body.get('data');total=body.get('total')
   if not isinstance(rows,list) or len(rows)!=total or total>=300:raise RuntimeError('Order pagination incomplete')
   filters=body.get('filterModel') or {}
   if str((filters.get('product_id') or {}).get('filter'))!=p['pid']:raise RuntimeError('Order filter product mismatch')
   expected=dict(dateFrom='2026-10-14',dateTo='2026-10-16',type='inRange',filterType='date')
   if filters.get('order_dt')!=expected:raise RuntimeError('Order-date filter mismatch')
   item=dict(nm_id=p['nm_id'],article=p['article'],source_snapshot_id=p['snapshot_id'],observed_at=obs['observed_at'])
   for label,day in (('before','2026-10-14'),('after','2026-10-16')):
    item[label]=cohort(rows,p['nm_id'],p['article'],day,own.get(p['article'].casefold()))
    item[label]['order_date']=day
   out.append(item)
  result=dict(status='calculated_order_contribution',products=out,orders_basis='order_dt',profit_basis='realized order-linked contribution before advertising and unallocated expenses',final_net_profit_available=False,telegram_calls=0,wb_writes=0)
  self.save('china_agent:order_cohort_calculated:2026-10-17',result)
  print(json.dumps(dict(products=len(out),status=result['status'],telegram_calls=0,wb_writes=0)))
if __name__=='__main__':
 w=Calculate('control')
 try:w.calculate()
 finally:
  import requests
  requests.sessions.Session.request=w.original_http
