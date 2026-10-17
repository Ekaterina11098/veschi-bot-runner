"""Owner-approved retained-manifest preflight. GET-only; no MPStats/WB/TG."""
import sys,os,json,hashlib,subprocess,requests
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from analytics.collect import _database_transport as db
from analytics.payload_storage import decode_rows,unpack
from analytics.mpstats_recovery import normalize
from stock_deploy_support import seal,error
IDS=[17841,17842,17843,17844,17845,17847,17849,17851,17853]
BLOBS={"advertising_source_owner.py":"80993de6ebb8cddc86d50c5285d14367552ed185","advertising_daily_owner.py":"9334338aa0796ee390ec7180f158aaacce745673","advertising_daily_continue.json":"e805e11feb148a940d8762de2e5cb0c7cc316328",".github/workflows/advertising-daily-prepared.yml":"245b4c86dc5e8d9b16bc4332bd79e54099ff0030"}
r=dict(complete=False,source_calls=0,wb_calls=0,telegram_calls=0,db_writes=0,snapshots=[],http_decoded_bytes=0)
def sha(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def claim():
 rows=db('GET','telegram_api_cache',params={'cache_key':'eq.advertising:ip:daily_run:v1:2026-10-17','select':'payload,updated_at','limit':1}) or []
 if len(rows)!=1:raise RuntimeError('Daily claim absent/ambiguous')
 return rows[0]
original=requests.sessions.Session.request
def guarded(session,method,url,*args,**kw):
 from urllib.parse import urlsplit
 if method!='GET' or urlsplit(url).hostname!=urlsplit(os.environ['SUPABASE_URL']).hostname:raise PermissionError('Preflight GET-only retained DB boundary')
 response=original(session,method,url,*args,**kw);r['http_decoded_bytes']+=len(response.content)
 return response
try:
 for path,expected in BLOBS.items():
  data=Path(path).read_bytes();actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
  if actual!=expected:raise RuntimeError('Prepared source/profile/workflow blob changed: '+path)
 r['verified_blobs']=BLOBS
 actual_private=subprocess.check_output(['git','rev-parse','HEAD'],cwd='private-source',text=True).strip()
 if actual_private!='6eb5f990aecfa1a92909169ffd76f05ac6da469d':raise RuntimeError('Private analytical pin changed')
 profile=json.loads(Path('advertising_daily_continue.json').read_text())
 if profile['enabled'] is not False or profile['from_run_id']!='39014867561:1':raise RuntimeError('Unexpected continuation profile state')
 manifest=profile['retained_source_manifest']
 if manifest!={'day':'2026-10-17','original_run_id':'39004453781:1','snapshot_ids':IDS}:raise RuntimeError('Full retained manifest changed')
 requests.sessions.Session.request=guarded
 initial_claim=claim();c=initial_claim['payload']
 if c.get('day')!='2026-10-17' or c.get('run_id')!='39014867561:1' or c.get('status')!='failed' or c.get('stages')!=[]:raise RuntimeError('Expected terminal daily claim/stages changed')
 legs=c.get('continuations') or []
 if len(legs)!=1 or legs[0].get('from_run')!='39004453781:1' or legs[0].get('to_run')!='39014867561:1':raise RuntimeError('Continuation lineage changed')
 if c.get('wb_mutations') is not False or c.get('forecasts') is not False:raise RuntimeError('Unsafe claim flags')
 r['daily_claim']=initial_claim
 params={'id':'in.('+','.join(map(str,IDS))+')','select':'id,source,cabinet,run_id,status,period_from,period_to,collected_at,payload','order':'id.asc','limit':9}
 first=decode_rows(db('GET','analytics_snapshots',params=params) or [])
 if [x['id'] for x in first]!=IDS:raise RuntimeError('Nine exact retained IDs not present')
 mirrors=db('GET','telegram_api_cache',params={'cache_key':'in.('+','.join('analytics:payload:'+str(i) for i in IDS)+')','select':'cache_key,payload,updated_at','limit':9}) or []
 mirrored={int(x['cache_key'].rsplit(':',1)[1]):x for x in mirrors}
 observers=db('GET','telegram_api_cache',params={'cache_key':'eq.advertising:ip:order_outcome_monitor:v1','select':'payload,updated_at','limit':1}) or []
 if len(observers)!=1:raise RuntimeError('Observer missing')
 m=observers[0]['payload'];history_ids={x.get('snapshot_id') for x in m.get('history',[])}
 if not set(IDS[:4]).issubset(history_ids):raise RuntimeError('Four prior observer ingestions not evidenced')
 r['observer_before_sha256']=sha(m);r['observer_tracked']=len(m.get('orders',{}));r['ingestion_replayed']=False
 expected_orders={17841:('139147637','2026-10-03','2026-10-03',1123677454),17842:('124391695','2026-09-17','2026-09-18',320248210),17843:('124391695','2026-09-22','2026-09-23',320248210),17844:('124391695','2026-09-27','2026-09-27',320248210)}
 for row in first:
  ident=row['id'];payload=row['payload']
  if row['run_id']!='39004453781:1' or row['cabinet']!='token_2' or row['status']!='complete' or not isinstance(payload,list) or len(payload)!=1:raise RuntimeError('Retained row identity/status mismatch: '+str(ident))
  obs=payload[0];args=obs.get('arguments') or {}
  if obs.get('status')!='received' or obs.get('scope_verified') is not True:raise RuntimeError('Retained observation unverified')
  if ident in expected_orders:
   pid,a,b,nm=expected_orders[ident];data=obs.get('data') or {};items=data.get('data');f=data.get('filterModel') or {}
   if obs.get('tool')!='lk_wb_card_orders' or args!={'type':'products','value':pid,'date_from':a,'date_to':b,'start_row':0,'end_row':300}:raise RuntimeError('Order request scope mismatch')
   if not isinstance(items,list) or data.get('total')!=len(items) or f.get('product_id',{}).get('filter')!=int(pid) or f.get('order_dt',{}).get('dateFrom')!=a or f.get('order_dt',{}).get('dateTo')!=b:raise RuntimeError('Order response incomplete/filter mismatch')
   ids=[str(x.get('gnumber') or '') for x in items]
   if '' in ids or len(ids)!=len(set(ids)) or any(x.get('nm_id')!=nm or not a<=x['order_dt'][:10]<=b for x in items):raise RuntimeError('Order identity/nm/date mismatch')
   if any(gn not in m['orders'] for gn in ids):raise RuntimeError('Previously ingested GN missing from observer')
  elif ident in (17845,17847,17849,17851):
   a={17845:'2026-10-16',17847:'2026-10-15',17849:'2026-10-14',17851:'2026-10-13'}[ident];b=a
   body=(obs.get('data') or {}).get('data') or {}
   if obs.get('tool')!='lk_wb_products' or args.get('date_from')!=a or args.get('date_to')!=a or body.get('need_update')!=0 or body.get('total')!=len(body.get('data') or []):raise RuntimeError('Retained daily finance scope/completeness mismatch')
  else:
   a='2026-10-10';b='2026-10-16'
   if obs.get('tool')!='wbbidder_campaigns' or args.get('report')!='stats' or args.get('start_row')!=0 or args.get('d1')!=a or args.get('d2')!=b:raise RuntimeError('Catalog scope mismatch')
  if row['period_from']!=a or row['period_to']!=b:raise RuntimeError('Stored/request period mismatch')
  normalized_source,normalized=normalize(obs,'token_2')
  mirror=mirrored.get(ident);mirror_ok=None
  if mirror:
   decoded=unpack(mirror['payload'])
   if sha(decoded)!=sha(payload):raise RuntimeError('Shared gzip/SHA mirror differs from immutable snapshot')
   mirror_ok=True
  r['snapshots'].append(dict(id=ident,run_id=row['run_id'],source=row['source'],request_key=obs['request_key'],
   period_from=a,period_to=b,observed_at=obs['observed_at'],payload_sha256=sha(payload),shared_mirror_sha_verified=mirror_ok,
   normalized_source=normalized_source,normalization_valid=True,external_recollection=False))
 second=decode_rows(db('GET','analytics_snapshots',params=params) or [])
 if sha(first)!=sha(second):raise RuntimeError('Retained snapshots changed across independent full readbacks')
 observer_again=db('GET','telegram_api_cache',params={'cache_key':'eq.advertising:ip:order_outcome_monitor:v1','select':'payload,updated_at','limit':1})
 if observer_again!=observers or claim()!=initial_claim:raise RuntimeError('Observer or day claim changed during read-only preflight')
 r['manifest_sha256']=sha(manifest);r['all_snapshots_full_readback']=True;r['claim_unchanged']=True;r['observer_unchanged']=True;r['complete']=True
except Exception as exc:r['error']=error(exc)
finally:
 requests.sessions.Session.request=original;seal('retained-full-preflight',r)
 print(json.dumps({'complete':r['complete'],'error_type':r.get('error',{}).get('type'),'source_calls':0,'db_writes':0,'snapshots_verified':len(r['snapshots'])}))
