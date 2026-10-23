"""Exactly one approved day-report request, through existing MPStats reader."""
import os,sys,json,copy,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import requests
sys.path.insert(0,str(Path.cwd()));sys.path.insert(0,'private-source')
from stock_deploy_support import seal,error
from advertising_agent import agent_store as s
from analytics.mpstats_probe import discover
from analytics.mpstats_gaps import execute_reads
from analytics.mpstats_recovery import normalize,BIDDER
from analytics.payload_storage import decode_rows
DAY='2026-10-21';CID=11861069;WB=37757330
KEY='advertising:ip:addressed37721:approved:20261023:v1'
proof=dict(complete=False,report_requests=0,source_report_scope=dict(campaign_id=CID,wb_campaign_id=WB,d1=DAY,d2=DAY,report='days'),wb_writes=0,telegram_calls=0,other_campaign_reads=0,full_collection=False)
native=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
def guard(session,method,url,*a,**kw):
 u=urlparse(url)
 if u.hostname==host and u.path.startswith('/rest/v1/'):pass
 elif u.hostname=='mcp.mpstats.io' and method.upper()=='POST':
  body=kw.get('json') or {};m=body.get('method')
  if m=='tools/call':
   p=body.get('params') or {};name=p.get('name');args=p.get('arguments') or {}
   if name=='wbbidder_campaign_stats':
    if args!={'campaign_id':CID,'report':'days','d1':DAY,'d2':DAY}:raise PermissionError('Exact approved day scope only')
    proof['report_requests']+=1
    if proof['report_requests']>1:raise PermissionError('One report request only')
    s.cache_set(KEY,dict(status='request_started',run_id=os.environ['GITHUB_RUN_ID'],at=datetime.now(timezone.utc).isoformat()),ttl_days=365)
   elif name=='lk_wb_cabinets':
    if args!={'action':'list'}:raise PermissionError('No cabinet switching')
   elif name!='account_limits':raise PermissionError('Other tools forbidden')
  elif m not in ('initialize','notifications/initialized'):raise PermissionError('Use saved tool catalog only')
 else:raise PermissionError('WB, Telegram and other sources forbidden')
 return native(session,method,url,*a,**kw)
requests.sessions.Session.request=guard
try:
 if str(datetime.now(ZoneInfo('Europe/Moscow')).date())!='2026-10-23':raise PermissionError('Approved date expired')
 prior=s.cache_get(KEY)
 if prior:raise PermissionError('Existing addressed claim; no automatic repeat')
 proof['daily_source_stages_finished']=True
 rows=s.db('POST','telegram_api_cache',params={'on_conflict':'cache_key'},body={'cache_key':KEY,'payload':{'status':'claimed','run_id':os.environ['GITHUB_RUN_ID']},'updated_at':datetime.now(timezone.utc).isoformat(),'expires_at':(datetime.now(timezone.utc)+timedelta(days=365)).isoformat()},prefer='resolution=ignore-duplicates,return=representation') or []
 if len(rows)!=1:raise RuntimeError('Addressed request claim conflict')
 pause=s.db('GET','telegram_api_cache',params={'cache_key':'eq.mpstats:cooldown','expires_at':'gt.'+datetime.now(timezone.utc).isoformat(),'select':'expires_at','limit':1}) or []
 if pause:
  wait=max(0,(datetime.fromisoformat(pause[0]['expires_at'].replace('Z','+00:00'))-datetime.now(timezone.utc)).total_seconds())
  if wait>600:raise RuntimeError('Shared RetryAfter exceeds bounded one-request window')
  if wait:time.sleep(wait+2)
 tools=s.db('GET','analytics_snapshots',params={'source':'eq.mpstats_connection','cabinet':'eq.shared','select':'tools:payload->0->tools','order':'id.desc','limit':1}) or []
 catalog=tools[0].get('tools') if tools else None
 if not catalog:raise RuntimeError('Saved tool catalog missing')
 bidder=copy.deepcopy(BIDDER);bidder['token_2']['campaign_ids']=[CID]
 def save(cabinet,obs):
  assert cabinet=='token_2'
  fields=dict(cabinet='token_2',run_id=os.environ['GITHUB_RUN_ID'],period_from=DAY,period_to=DAY)
  raw=s.db('POST','analytics_snapshots',body=dict(fields,source='mpstats_'+obs['tool'],status='complete' if obs['status']=='received' else 'partial',payload=[obs],detail='Owner approved ONE exact day request for WB37757330; no repeated other collection'),prefer='return=representation') or []
  if len(raw)!=1:raise RuntimeError('Raw response persistence failed')
  got=s.db('GET','analytics_snapshots',params={'id':'eq.'+str(raw[0]['id']),'select':'id,payload','limit':1}) or []
  if not got or got[0]['payload']!=[obs]:raise RuntimeError('Raw response full readback mismatch')
  proof['raw_snapshot_id']=raw[0]['id'];proof['observation']=obs
  if obs.get('retry_after'):
   s.db('POST','telegram_api_cache',params={'on_conflict':'cache_key'},body={'cache_key':'mpstats:cooldown','payload':{'pending':True,'retry_after':obs['retry_after']},'updated_at':datetime.now(timezone.utc).isoformat(),'expires_at':(datetime.now(timezone.utc)+timedelta(seconds=obs['retry_after'])).isoformat()},prefer='resolution=merge-duplicates')
  if obs['status']!='received':return
  source,p=normalize(obs,cabinet);p['raw_snapshot_id']=raw[0]['id']
  result=s.db('POST','analytics_snapshots',body=dict(fields,source=source,status='complete',payload=[p],detail='Approved exact-day campaign aggregate; no inferred SKU allocation'),prefer='return=representation') or []
  if len(result)!=1:raise RuntimeError('Normalized response persistence failed')
  rb=decode_rows(s.db('GET','analytics_snapshots',params={'id':'eq.'+str(result[0]['id']),'select':'id,payload','limit':1}) or [])
  if not rb or rb[0]['payload']!=[p]:raise RuntimeError('Normalized full readback mismatch')
  proof['normalized_snapshot_id']=result[0]['id'];proof['normalized']=p;proof['complete']=True
 plan=[dict(cabinet='token_2',tool='wbbidder_campaign_stats',key='owner-approved37721:20261023:days',priority=100,arguments={'campaign_id':CID,'report':'days','d1':DAY,'d2':DAY})]
 def reader(call,checks,known):return execute_reads(call,checks,known,plan,bidder,save,max_requests=1)
 proof['provider']=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=reader,catalog=catalog)
 if proof['provider'].get('retry_after'):
  s.db('POST','telegram_api_cache',params={'on_conflict':'cache_key'},body={'cache_key':'mpstats:cooldown','payload':{'pending':True,'retry_after':proof['provider']['retry_after']},'expires_at':(datetime.now(timezone.utc)+timedelta(seconds=proof['provider']['retry_after'])).isoformat()},prefer='resolution=merge-duplicates')
 s.cache_set(KEY,dict(status='complete' if proof['complete'] else 'incomplete',run_id=os.environ['GITHUB_RUN_ID'],report_requests=proof['report_requests'],raw_snapshot_id=proof.get('raw_snapshot_id'),normalized_snapshot_id=proof.get('normalized_snapshot_id'),no_automatic_retry=True),ttl_days=365)
except Exception as exc:proof['error']=error(exc)
finally:
 seal('approved37721-day',proof)
 print(json.dumps({k:proof.get(k) for k in ('complete','report_requests','raw_snapshot_id','normalized_snapshot_id','wb_writes','telegram_calls')}))
if not proof['complete']:raise SystemExit(1)
