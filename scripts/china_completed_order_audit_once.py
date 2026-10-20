import os,json
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from china_price_apply import IO
from analytics.mpstats_probe import discover,unpack_tool,sanitize,ProbeError
io=IO();now=datetime.now(timezone.utc);key='china_agent:completed_order_audit:2026-10-20:v1'
cooldown=io.db('telegram_api_cache?cache_key=eq.mpstats:cooldown&expires_at=gt.'+now.isoformat().replace('+00:00','Z')+'&select=cache_key')
if cooldown:raise RuntimeError('Shared MPStats cooldown active')
def read(call,checks,seen):
    def tool(name,args):return sanitize(unpack_tool(call('tools/call',dict(name=name,arguments=args))))
    cabinets=checks['lk_wb_cabinets'];selected=[x['id'] for x in cabinets if x.get('selected')]
    if len(selected)>1:raise ProbeError('Ambiguous original scope')
    matches=[x for x in cabinets if x.get('id')==10026946 and x.get('name')=='VESCHI Гонконг' and x.get('valid') is True]
    if len(matches)!=1:raise ProbeError('China identity mismatch')
    today=datetime.now(ZoneInfo('Europe/Moscow')).date()
    result=dict(cabinet='token_3',mpstats_cabinet_id=10026946,observed_at=now.isoformat(),reports={},wb_writes=0)
    try:
        tool('lk_wb_cabinets',dict(action='select',id=10026946))
        if [x['id'] for x in tool('lk_wb_cabinets',dict(action='list')) if x.get('selected')]!=[10026946]:raise ProbeError('Scope unverified')
        for name,args in [
            ('lk_wb_sales_tape',dict(date_from='2026-09-20',date_to='2026-10-19',start_row=0,end_row=1500)),
            ('lk_wb_products',dict(date_from='2026-09-20',date_to='2026-10-19',start_row=0,end_row=1500)),
            ('lk_wb_reports_weekly',dict(period_type='30days'))

        ]:
            if name not in seen:result['reports'][name]=dict(status='unavailable');continue
            try:result['reports'][name]=dict(status='received',arguments=args,data=tool(name,args),period_status='requested_only')
            except ProbeError as ex:
                result['reports'][name]=dict(status=ex.status,detail=ex.detail)
                if ex.retry_after:raise
    finally:
        tool('lk_wb_cabinets',dict(action='select',id=selected[0]) if selected else dict(action='reset'))
    return result
r=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=read)
data=dict(status=r.get('status'),extra_reads=r.get('extra_reads'),detail=r.get('detail'),retry_after=r.get('retry_after'),wb_writes=0)
if r.get('retry_after'):
    until=now+timedelta(seconds=r['retry_after'])
    io.db('telegram_api_cache?on_conflict=cache_key','POST',dict(cache_key='mpstats:cooldown',payload=dict(pending=True),expires_at=until.isoformat()),'resolution=merge-duplicates')
data['own_costs']=io.db('analytics_costs?select=article,cost,observed_at,source&limit=5000')
io.create(key,data)
print(json.dumps(dict(status=data['status'],reports={k:v.get('status') for k,v in (data.get('extra_reads') or {}).get('reports',{}).items()},wb_writes=0)))
