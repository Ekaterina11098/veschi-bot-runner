import sys,os,json,requests
from datetime import datetime,timezone
sys.path[:0]=['scripts','source']
from china_price_apply import IO
from wb_bot.mpstats_probe import discover
from wb_bot.mpstats_gaps import execute_reads
io=IO();saved=[];key='china_agent:loss_preview_source:2026-10-23:v1'
def reader(call,checks,known):
 def save(cab,o):saved.append(o)
 request=dict(key='loss-preview-30-full-days',cabinet='token_3',tool='lk_wb_products',arguments=dict(date_from='2026-09-23',date_to='2026-10-22',start_row=0,end_row=300))
 return execute_reads(call,checks,known,[request],{},save,max_requests=1)
r=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=reader)
out=dict(status=r['status'],observed_at=datetime.now(timezone.utc).isoformat(),period_from='2026-09-23',period_to='2026-10-22',cabinet='token_3',observations=saved,wb_writes=0,telegram_calls=0)
# Current full WB seller prices, one GET; no upload endpoint is used.
p=io.wb('/api/v2/list/goods/filter?limit=1000&offset=0')
if len(p.get('listGoods',[]))>=1000:raise ValueError('Price pagination required')
out['prices']=p.get('listGoods',[])
io.create(key,out)
print(json.dumps(dict(status=out['status'],observations=[o['status'] for o in saved],price_rows=len(out['prices']),wb_writes=0,telegram_calls=0)))
