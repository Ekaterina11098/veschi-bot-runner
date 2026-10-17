"""Acquire order-linked China facts for price cohort correction; no delivery."""
import os,json
from datetime import datetime,timezone
from urllib.parse import urlparse
from china_agent.control_owner_preview import Preview
from china_agent.morning_pair import tracked_rows
from china_agent import demand
from analytics.mpstats_primary import products
from analytics.mpstats_probe import discover
from analytics.mpstats_gaps import execute_reads
class Cohort(Preview):
 def collect(self):
  read=lambda t,p:self.db('GET',t,params=p)
  state=self.get(demand.STATE_KEY) or {};tracked=tracked_rows(state,self.day)
  rows,marker=products(read,'token_3','2026-10-13','2026-10-16',datetime.now(timezone.utc))
  ids={str(r['nm_id']):str(r['p_id']) for r in rows}
  # Previously independently reconciled extended catalogue mapping.
  ids['1535337777']='149503571'
  reqs=[];targets={}
  for nm,e,c,d in tracked:
   if str(nm) not in ids:raise RuntimeError('Missing cohort product mapping')
   key='cohort:'+str(nm);targets[key]=(str(nm),e['article'],ids[str(nm)])
   reqs.append(dict(cabinet='token_3',tool='lk_wb_card_orders',key=key,priority=90,arguments=dict(type='products',value=ids[str(nm)],date_from='2026-10-14',date_to='2026-10-16',start_row=0,end_row=300)))
  observations=[]
  def save(cabinet,obs):
   if cabinet!='token_3' or not obs.get('scope_verified') or obs['request_key'] not in targets:raise RuntimeError('Cohort identity mismatch')
   nm,article,pid=targets[obs['request_key']]
   marker=dict(source='mpstats_lk_wb_card_orders',cabinet=cabinet,run_id='china-order-cohort-'+os.environ['GITHUB_RUN_ID'],period_from='2026-10-14',period_to='2026-10-16',detail='Order-date cohort evidence; no sale-date allocation')
   receipt=self.db('POST','analytics_snapshots',body=dict(marker,status='complete' if obs['status']=='received' else 'error',payload=[obs]),prefer='return=representation') or []
   observations.append(dict(nm_id=nm,article=article,pid=pid,snapshot_id=receipt[0]['id'] if receipt else None,observation=obs))
   self.save('china_agent:order_cohort_raw:2026-10-17',dict(status='acquiring',products=observations,telegram_calls=0,wb_writes=0))
   if obs.get('retry_after'):self.save('mpstats:cooldown',dict(pending=True),max(1,obs['retry_after'])/86400)
  def extra(call,checks,known):return execute_reads(call,checks,known,reqs,{},save,max_requests=28)
  r=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=extra)
  self.save('china_agent:order_cohort_raw:2026-10-17',dict(status='acquired' if len(observations)==len(reqs) and all(p['observation']['status']=='received' for p in observations) else 'incomplete',products=observations,connection_status=r['status'],telegram_calls=0,wb_writes=0))
  print(json.dumps(dict(requested=len(reqs),received=len(observations),connection=r['status'],wb_writes=0,telegram_calls=0)))
if __name__=='__main__':
 w=Cohort('control')
 try:w.collect()
 finally:
  import requests
  requests.sessions.Session.request=w.original_http
