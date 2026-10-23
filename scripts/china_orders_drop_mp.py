import os,json
from datetime import datetime,timezone
from analytics.mpstats_probe import discover
from analytics.mpstats_gaps import execute_reads
from advertising_agent.notify import cache_get,cache_set
KEY='china_agent:orders_drop:2026-10-23:mp:v1'
if cache_get(KEY):print('Existing audit preserved');raise SystemExit(0)
out=dict(cabinet='token_3',observed_at=datetime.now(timezone.utc).isoformat(),reports=[],wb_writes=0,telegram_calls=0)
def save(cab,o):out['reports'].append(o);cache_set(KEY,out,365)
pending=[]
for label,a,b in [('eight_days','2026-10-15','2026-10-22'),('day21','2026-10-21','2026-10-21'),('day22','2026-10-22','2026-10-22')]:
 pending.append(dict(cabinet='token_3',tool='lk_wb_products',arguments=dict(date_from=a,date_to=b,start_row=0,end_row=1500),key=label,priority=90))
pending.append(dict(cabinet='token_3',tool='lk_wb_dashboard_table',arguments=dict(date_from='2026-10-15',date_to='2026-10-22',period_type='custom'),key='daily_cabinet',priority=80))
try:
 def reader(call,checks,known):return execute_reads(call,checks,known,pending,{},save,max_requests=8)
 z=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=reader);out['connection']={k:z.get(k) for k in ['status','connected','detail','retry_after']}
except Exception as e:out['error']=type(e).__name__
out['completed_at']=datetime.now(timezone.utc).isoformat();cache_set(KEY,out,365);print(json.dumps(dict(saved=True,reports=len(out['reports']),error=out.get('error'),wb_writes=0,telegram_calls=0)))
