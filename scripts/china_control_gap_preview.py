"""Read missing card's explicit daily metrics, no delivery."""
import os,json
from urllib.parse import urlparse
from china_agent.control_owner_preview import Preview
from analytics.mpstats_probe import discover
from analytics.mpstats_gaps import execute_reads
class Gap(Preview):
 def guard(self,session,method,url,*a,**kw):
  if urlparse(url).hostname=='mcp.mpstats.io':
   body=kw.get('json') or {};p=body.get('params') or {}
   if body.get('method')=='tools/call' and p.get('name')=='lk_wb_card_table':
    if p.get('arguments')!=dict(type='products',value='149503571',period_type='30days',self_redemption=False):raise RuntimeError('Card scope mismatch')
    return self.original_http(session,method,url,*a,**kw)
  return super().guard(session,method,url,*a,**kw)
 def acquire_gap(self):
  def save(cabinet,obs):
   if cabinet!='token_3' or not obs.get('scope_verified'):raise RuntimeError('Cabinet mismatch')
   self.db('POST','analytics_snapshots',body=dict(source='mpstats_'+obs['tool'],cabinet=cabinet,run_id='china-control-gap-'+os.environ['GITHUB_RUN_ID'],period_from='2026-10-14',period_to='2026-10-16',status='complete' if obs['status']=='received' else 'error',payload=[obs],detail='Missing control card explicit daily data'))
   self.save('china_agent:control_gap_card:2026-10-17',obs)
  def extra(call,checks,known):
   req=dict(cabinet='token_3',tool='lk_wb_card_table',key='china-control-gap:1535337777',arguments=dict(type='products',value='149503571',period_type='30days',self_redemption=False),priority=90)
   return execute_reads(call,checks,known,[req],{},save,max_requests=1)
  r=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=extra)
  self.save('china_agent:control_gap_tools:2026-10-17',dict(tools=[t for t in r.get('tools',[]) if t['name'] in ('lk_wb_card_widget','lk_wb_card_info','lk_wb_card_table')]))
  print(json.dumps(dict(status=r['status'],telegram_calls=0,wb_writes=0)))
if __name__=='__main__':
 w=Gap('control')
 try:w.acquire_gap()
 finally:
  import requests
  requests.sessions.Session.request=w.original_http
