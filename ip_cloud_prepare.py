"""Publish compact question evidence once; only retained Supabase data, never a collector."""
import os,sys,json
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit
import requests
sys.path.insert(0,str(Path(__file__).resolve().parent/'private-source'))
from advertising_agent import agent_store as store
from ip_cloud_dialog import State,ROOT,publish_context,mskday

def main():
 s=State(store);day=str(datetime.fromisoformat(mskday()).date()-timedelta(days=1));pointer=s.get(ROOT+'latest')or{}
 if pointer.get('period')==day:return {'status':'compact_cache_reused','period':day}
 host=urlsplit(os.environ['SUPABASE_URL']).hostname;native=requests.sessions.Session.request
 def guard(session,method,url,*a,**kw):
  if urlsplit(url).hostname!=host:raise RuntimeError('Preparation is saved-data only')
  return native(session,method,url,*a,**kw)
 requests.sessions.Session.request=guard
 try:
  recovery=s.store.cache_get('advertising:ip:morning_recovery:'+mskday()+':v1')or{}
  if recovery.get('status')=='complete'and recovery.get('data_day')==day:view=recovery['view']
  else:
   from advertising_budget_evidence import load_daily_table_view
   from datetime import timezone
   view=load_daily_table_view(store,datetime.now(timezone.utc))
  recent=[]
  for back in(2,1):
   date=str(datetime.fromisoformat(mskday()).date()-timedelta(days=back))
   old=store.cache_get('advertising:ip:morning_recovery:'+date+':v1')or{}
   if old.get('view'):recent.append(old['view'])
  # Frozen delivered plan is canonical, not the larger image preview cache.
  plan=store.cache_get('advertising:ip:daily-png-plan:v1:'+day)or{}
  publish_context(store,view,plan,recent)
  return {'status':'compact_cache_prepared','period':day,'source_calls':0,'wb_writes':0}
 finally:requests.sessions.Session.request=native
if __name__=='__main__':print(json.dumps(main()))

