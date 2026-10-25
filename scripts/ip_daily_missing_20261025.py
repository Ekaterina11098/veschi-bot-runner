"""Owner-authorized exact IP gaps through existing execute_reads; no analysis/send/WB."""
import os,sys,json,copy,time,hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import requests
sys.path.insert(0,str(Path.cwd()));sys.path.insert(0,'private-source')
from advertising_agent import agent_store as s
from analytics.mpstats_probe import discover
from analytics.mpstats_gaps import execute_reads,period
from analytics.mpstats_recovery import normalize,BIDDER
from analytics.payload_storage import decode_rows
from stock_deploy_support import seal,error
MAPPING={35654841:11435350,36514081:11602333,37155100:11736035,37363108:11779755,37757330:11861069,39410834:12102131,39483230:12103480,39634287:12107512,40192945:12190110,40428505:12221548,40428689:12221549}
KEY='advertising:ip:approved-missing-products:20261025:v1'
proof=dict(complete=False,wb_writes=0,telegram_calls=0,full_collection=False,report_requests=0,decoded_bytes=0,limit_bytes=100_000_000,saved=[],pending=[],attempts=[])
args=[dict(campaign_id=cid,report='products',d1='2026-10-24',d2='2026-10-24') for cid in MAPPING.values()]
args.append(dict(campaign_id=11861069,report='days',d1='2026-10-24',d2='2026-10-24'))
args.extend(dict(tokens=[152922],report=kind,d1='2026-10-18',d2='2026-10-24',bidder_only=False,start_row=100,limit=100,sort='wb_id',sort_dir='asc') for kind in ['stats','state'])
canonical=lambda a:json.dumps(a,sort_keys=True)
allowed={canonical(a) for a in args}
plan=[dict(cabinet='token_2',tool=('wbbidder_campaigns' if 'tokens' in a else 'wbbidder_campaign_stats'),key='owner-ip-gap-20261025:'+canonical(a),priority=100,arguments=a) for a in args]
native=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
deadline=time.monotonic()+1200
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def persist(status):
 value=dict(status=status,run_id=os.environ['GITHUB_RUN_ID'],pending=proof['pending'],completed=proof['saved'],report_requests=proof['report_requests'],decoded_bytes=proof['decoded_bytes'],updated_at=datetime.now(timezone.utc).isoformat())
 s.cache_set(KEY,value,ttl_days=365)
 if s.cache_get(KEY)!=value:raise RuntimeError('Gap progress full readback failed')
 seal('approved-ip-report-repair-20261025',proof)
def guard(session,method,url,*a,**kw):
 u=urlparse(url)
 if u.hostname==host and u.path.startswith('/rest/v1/'):pass
 elif u.hostname=='mcp.mpstats.io' and method.upper()=='POST':
  if proof['decoded_bytes']>=proof['limit_bytes']:raise RuntimeError('100MB threshold; stop new source reads')
  body=kw.get('json') or {};m=body.get('method')
  if m=='tools/call':
   p=body.get('params') or {};name=p.get('name');a2=p.get('arguments') or {}
   if name in ('wbbidder_campaign_stats','wbbidder_campaigns'):
    if canonical(a2) not in allowed:raise PermissionError('Outside explicitly approved missing scope')
    proof['report_requests']+=1
    if proof['report_requests']>42:raise RuntimeError('Bounded read attempts exhausted')
   elif name=='lk_wb_cabinets':
    if a2!={'action':'list'}:raise PermissionError('Cabinet switching prohibited')
   elif name!='account_limits':raise PermissionError('Other MPStats tools prohibited')
  elif m not in ('initialize','notifications/initialized'):raise PermissionError('Saved tool catalog only')
 else:raise PermissionError('WB/Telegram/other hosts forbidden')
 response=native(session,method,url,*a,**kw)
 proof['decoded_bytes']+=len(response.content)
 return response
requests.sessions.Session.request=guard
try:
 if str(datetime.now(ZoneInfo('Europe/Moscow')).date())!='2026-10-25':raise PermissionError('Authorized date expired')
 if s.cache_get(KEY):raise PermissionError('Existing gap claim; no automatic duplicate run')
 reg=s.registration()
 if reg['chat_id']!=-1004378639510:raise PermissionError('Registered IP scope mismatch')
 claim=s.db('POST','telegram_api_cache',params={'on_conflict':'cache_key'},body={'cache_key':KEY,'payload':{'status':'claimed','run_id':os.environ['GITHUB_RUN_ID']},'updated_at':datetime.now(timezone.utc).isoformat(),'expires_at':(datetime.now(timezone.utc)+timedelta(days=365)).isoformat()},prefer='resolution=ignore-duplicates,return=representation') or []
 if len(claim)!=1:raise PermissionError('One source executor only')
 rows=s.db('GET','analytics_snapshots',params={'source':'eq.mpstats_connection','cabinet':'eq.shared','select':'tools:payload->0->tools','order':'id.desc','limit':1}) or []
 catalog=rows[0].get('tools') if rows else None
 if not catalog:raise RuntimeError('Saved MPStats tool catalog absent')
 bidder=copy.deepcopy(BIDDER);bidder['token_2']['campaign_ids']=list(MAPPING.values())
 pending=list(plan);done=set();retry_keys=set();not_ready=set()
 def save(cabinet,obs):
  if cabinet!='token_2' or canonical(obs['arguments']) not in allowed:raise PermissionError('Observation outside owner scope')
  a,b=period(obs['arguments']);fields=dict(cabinet='token_2',run_id=os.environ['GITHUB_RUN_ID'],period_from=a,period_to=b)
  raw=s.db('POST','analytics_snapshots',body=dict(fields,source='mpstats_'+obs['tool'],status='complete' if obs['status']=='received' else 'partial',payload=[obs],detail='Owner-authorized IP missing exact-day report; no complete rerun/WB/Telegram'),prefer='return=representation') or []
  if len(raw)!=1:raise RuntimeError('Raw snapshot persistence failed')
  rb=decode_rows(s.db('GET','analytics_snapshots',params={'id':'eq.'+str(raw[0]['id']),'select':'id,payload','limit':1}) or [])
  if not rb or digest(rb[0]['payload'])!=digest([obs]):raise RuntimeError('Raw snapshot SHA readback mismatch')
  item=dict(key=obs['request_key'],raw_snapshot_id=raw[0]['id'],status=obs['status'])
  proof['attempts'].append(item)
  if obs.get('retry_after'):
   retry_keys.add(obs['request_key'])
   seconds=max(1,float(obs['retry_after']))
   s.db('POST','telegram_api_cache',params={'on_conflict':'cache_key'},body={'cache_key':'mpstats:cooldown','payload':{'pending':True,'retry_after':seconds},'updated_at':datetime.now(timezone.utc).isoformat(),'expires_at':(datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat()},prefer='resolution=merge-duplicates')
  if obs['status']=='received':
   if (obs.get('data') or {}).get('totals') is None and obs['arguments']['report']=='products':
    not_ready.add(obs['request_key']);proof.setdefault('unresolved',[]).append(dict(item,reason='Empty products response: no totals; not zero'));return
   source,p=normalize(obs,cabinet);p['raw_snapshot_id']=raw[0]['id']
   normalized=s.db('POST','analytics_snapshots',body=dict(fields,source=source,status='complete',payload=[p],detail='Exact approved IP gap; no inferred SKU allocation'),prefer='return=representation') or []
   if len(normalized)!=1:raise RuntimeError('Normalized persistence failed')
   rb=decode_rows(s.db('GET','analytics_snapshots',params={'id':'eq.'+str(normalized[0]['id']),'select':'id,payload','limit':1}) or [])
   if not rb or digest(rb[0]['payload'])!=digest([p]):raise RuntimeError('Normalized SHA readback mismatch')
   item.update(normalized_snapshot_id=normalized[0]['id'],full_readback=True)
   proof['saved'].append(item);done.add(obs['request_key'])
  elif not obs.get('retry_after'):raise RuntimeError('Source response failed; saved evidence; no automatic replay')
  proof['pending']=[r for r in pending if r['key'] not in done]
  persist('running')
 for attempt in range(3):
  pause=s.db('GET','telegram_api_cache',params={'cache_key':'eq.mpstats:cooldown','expires_at':'gt.'+datetime.now(timezone.utc).isoformat(),'select':'expires_at','limit':1}) or []
  if pause:
   delay=max(0,(datetime.fromisoformat(pause[0]['expires_at'].replace('Z','+00:00'))-datetime.now(timezone.utc)).total_seconds())+2
   if time.monotonic()+delay>deadline:raise RuntimeError('RetryAfter exceeds bounded continuation window')
   time.sleep(delay)
  retry_keys.clear()
  def reader(call,checks,known):return execute_reads(call,checks,known,pending,bidder,save,max_requests=20)
  provider=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=reader,catalog=catalog)
  proof['provider']={k:v for k,v in provider.items() if k not in ('tools','checks')}
  pending=[r for r in pending if r['key'] not in done]
  proof['pending']=pending
  if not pending:proof['complete']=True;break
  persist('incomplete')
  if not retry_keys or not provider.get('connected',False):break
  if time.monotonic()>deadline:break
 persist('complete' if proof['complete'] else 'incomplete')
except Exception as exc:proof['error']=error(exc)
finally:
 seal('approved-ip-report-repair-20261025',proof)
 print(json.dumps({k:proof.get(k) for k in ('complete','report_requests','decoded_bytes','wb_writes','telegram_calls')}))
if not proof['complete']:raise SystemExit(1)

