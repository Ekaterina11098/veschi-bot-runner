"""Saved-only Nov6 reviewed preview, exact Nov5 data. No WB, collectors, Telegram or delivery claims."""
import os,sys,json,copy,base64,hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
import requests
from analytics.collect import database,RUN_ID
from advertising_agent import agent_store as store
from ip_daily_png_contract import build_contract,render_recommendations
from ip_budget_table_png import render_budget_png
KEY='advertising:ip:restored-preview:2026-11-06:v1'
def put(p):database('POST','telegram_api_cache',params={'on_conflict':'cache_key'},body=dict(cache_key=KEY,payload=p,updated_at=datetime.now(timezone.utc).isoformat(),expires_at='2027-11-06T00:00:00Z'))
def main():
 native=requests.sessions.Session.request;host=urlsplit(os.environ['SUPABASE_URL']).hostname
 def guard(session,method,url,*a,**kw):
  if urlsplit(url).hostname!=host:raise PermissionError('Saved Supabase only')
  return native(session,method,url,*a,**kw)
 requests.sessions.Session.request=guard
 try:
  restored=store.cache_get('advertising:ip:morning_recovery:2026-11-06:v1') or {}
  if restored.get('status')!='complete' or restored.get('data_day')!='2026-11-05':raise ValueError('Full Nov5 restoration not ready')
  view=copy.deepcopy(restored['view'])
  if view['period']!='2026-11-05' or len(view['campaigns'])!=13 or any(c.get('metrics_complete')is not True for c in view['campaigns']):raise ValueError('13daily campaigns required')
  view['_recent_views']=[]
  for day in ('2026-11-04','2026-11-05'):
   old=store.cache_get('advertising:ip:morning_recovery:'+day+':v1') or {}
   if old.get('view'):view['_recent_views'].append(copy.deepcopy(old['view']))
  contract=build_contract(store,view)
  for c in view['campaigns']:c['campaign_name']=c.get('campaign_name') or contract['campaign_labels'].get(str(c['campaign_id']),{}).get('name') or ''
  out=Path(os.environ['RUNNER_TEMP'])/'ip-restored-nov6'
  imgs=[render_recommendations(view,contract,out)];second,bc=render_budget_png(view,out)
  if second:imgs.append(second)
  images=[]
  for item in imgs:
   raw=Path(item['path']).read_bytes()
   images.append(dict(kind=item['kind'],sha256=hashlib.sha256(raw).hexdigest(),data=base64.b64encode(raw).decode()))
  p=dict(status='preview_ready',run_id=RUN_ID,view=view,contract=contract,images=images,budget_coverage=bc,own_summary=restored.get('own_summary'),source_calls=0,wb_writes=0,telegram_calls=0,created_at=datetime.now(timezone.utc).isoformat())
  put(p);print(json.dumps(dict(status=p['status'],actions=len(contract['actions']),images=len(images),review=contract.get('review_coverage'))))
 except Exception as e:
  put(dict(status='blocked',error=str(e),run_id=RUN_ID,source_calls=0,wb_writes=0,telegram_calls=0));raise
 finally:requests.sessions.Session.request=native
if __name__=='__main__':main()
