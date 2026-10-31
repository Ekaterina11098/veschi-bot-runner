"""One bounded read of own completed China history; no WB/TG calls."""
import os,json
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,stamp
from analytics.mpstats_probe import discover
from analytics.mpstats_gaps import execute_reads
ROOT='china_agent:price143_unit_economics:2026-10-31:v1'
def run():
 c=Cache();q=c.get(ROOT+':read_request')or{};key=ROOT+':buyout30'
 if q.get('status')!='approved_read_only' or q.get('cabinet')!='token_3' or datetime.now(timezone.utc)>=datetime.fromisoformat(q['expires_at']):raise ValueError('Read authorization expired')
 if c.get(key):return
 found=[]
 tasks=[dict(cabinet='token_3',tool='lk_wb_products',key='owner-price143-completed31',priority=80,arguments=dict(date_from='2026-10-01',date_to='2026-10-30',start_row=0,end_row=1000))]
 def persist(cabinet,obs):
  if cabinet=='token_3' and obs.get('scope_verified')is True and obs.get('status')=='received':found.append(obs)
 def extra(call,checks,known):return execute_reads(call,checks,known,tasks,{},persist,max_requests=1)
 try:
  discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=extra)
  if len(found)!=1:raise ValueError('No one complete scoped observation')
  body=found[0].get('data',{}).get('data',{});rows=body.get('data',[])
  if body.get('need_update')!=0 or body.get('total')!=len(rows):raise ValueError('Products source not ready or incomplete')
  wanted={i['nm_id']for i in q['items']};fields=['nm_id','sa_name','finished_orders','is_payed','finish_as_return','not_finished_orders','average_delivery_cost','forwardlogisticsum','backwardlogisticsum','total_commission_without_spp_in_sales','is_payed_percent_after_returns','logistic_all','orders_count','orders_sum','sales_sum','returns_sum']
  selected=[{k:r.get(k)for k in fields}for r in rows if int(r['nm_id'])in wanted]
  value=dict(status='complete',period_from='2026-10-01',period_to='2026-10-30',observed_at=stamp(),source='MPStats verified own China products',currency='RUB',all_product_records=len(rows),rows=selected,missing_ids=sorted(wanted-{int(r['nm_id'])for r in selected}),wb_writes=0,telegram_calls=0)
 except Exception as ex:value=dict(status='unavailable',reason=str(ex)if isinstance(ex,ValueError)else type(ex).__name__,observed_at=stamp(),wb_writes=0,telegram_calls=0)
 if not c.create(key,value):raise ValueError('Duplicate result')
 print(json.dumps({k:v for k,v in value.items()if k not in ['rows']}))
if __name__=='__main__':run()
