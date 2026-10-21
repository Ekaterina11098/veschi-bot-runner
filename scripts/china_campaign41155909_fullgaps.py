"""Complete cabinet input gaps, read only; no Telegram or marketplace writes."""
import os,json,requests
from datetime import datetime,timezone
from china_price_apply import IO
from analytics.mpstats_probe import discover,unpack_tool,sanitize,ProbeError
from analytics.payload_storage import decode_rows
io=IO();key='china_agent:full_cabinet_gaps:2026-10-21:v1'
if io.get(key):print('Existing audit preserved');raise SystemExit()
out=dict(cabinet='token_3',observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_calls=0)
r=requests.get('https://common-api.wildberries.cn/api/v1/tariffs/commission',params={'locale':'ru'},headers={'Authorization':io.token},timeout=(10,60),allow_redirects=False)
out['commission']=dict(http_status=r.status_code)
if r.status_code==200:out['commission']['data']=sanitize(r.json())
cards=decode_rows(io.db('analytics_snapshots?cabinet=eq.token_3&source=eq.cards&status=eq.complete&select=id,payload,collected_at&order=id.desc&limit=1'))
out['cards']=cards
def reader(call,checks,seen):
 def tool(name,args):return sanitize(unpack_tool(call('tools/call',dict(name=name,arguments=args))))
 initial=[x['id'] for x in checks['lk_wb_cabinets'] if x.get('selected')]
 if len(initial)>1:raise ProbeError('Ambiguous cabinet')
 reports={}
 try:
  tool('lk_wb_cabinets',dict(action='select',id=10026946))
  if [x['id'] for x in tool('lk_wb_cabinets',dict(action='list')) if x.get('selected')]!=[10026946]:raise ProbeError('Wrong cabinet')
  for name,args in [('lk_wb_taxes',{}),('lk_wb_reports_compare',dict(d11='22.08.2026',d12='20.09.2026',d21='21.09.2026',d22='20.10.2026',show_all=True,size_group=False,start_row=0,end_row=1500))]:
   reports[name]=dict(arguments=args,data=tool(name,args))
 finally:tool('lk_wb_cabinets',dict(action='select',id=initial[0]) if initial else dict(action='reset'))
 return reports
result=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=reader)
out['reports']=result.get('extra_reads');out['status']=result['status'];out['error']=result.get('detail')
io.create(key,out)
print(json.dumps(dict(status=out['status'],commission_status=r.status_code,wb_writes=0,telegram_calls=0)))
