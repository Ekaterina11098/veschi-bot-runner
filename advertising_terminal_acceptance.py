"""Terminal acceptance: retained DB GET only, no business/source calls."""
import os,sys,json,hashlib,requests
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from analytics.collect import _database_transport as db
from analytics.payload_storage import decode_rows
from stock_deploy_support import seal,error
r=dict(source_calls=0,wb_calls=0,telegram_calls=0,db_writes=0,decoded_bytes=0)
native=requests.sessions.Session.request
def guarded(session,method,url,*a,**kw):
 if method.upper()!='GET' or urlsplit(url).hostname!=urlsplit(os.environ['SUPABASE_URL']).hostname:raise PermissionError('Retained Supabase GET only')
 v=native(session,method,url,*a,**kw);r['decoded_bytes']+=len(v.content)
 if r['decoded_bytes']>30000000:raise RuntimeError('Bounded acceptance read exceeded30MB')
 return v
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
try:
 requests.sessions.Session.request=guarded
 rows=decode_rows(db('GET','analytics_snapshots',params={'id':'eq.18018','select':'id,source,cabinet,payload,collected_at,run_id,period_from,period_to','limit':1}) or [])
 if len(rows)!=1:raise RuntimeError('Exact composed finance absent')
 f=rows[0];r['finance_marker']={k:v for k,v in f.items() if k!='payload'}
 r['finance_payload_sha256']=digest(f['payload'])
 r['finance_payload']=f['payload']
 for source in ('advertising_campaign_index','advertising_campaign_budgets','advertising_active_configuration'):
  params={'source':'eq.'+source,'cabinet':'eq.token_2','select':'id,collected_at,run_id,payload','order':'id.desc','limit':1}
  a=decode_rows(db('GET','analytics_snapshots',params=params) or [])
  b=decode_rows(db('GET','analytics_snapshots',params=params) or [])
  if digest(a)!=digest(b):raise RuntimeError('Readback changed:'+source)
  r[source]=a;r[source+'_sha256']=digest(a)
 params={'cache_key':'eq.advertising:ip:daily_run:v1:2026-10-17','select':'payload,updated_at','limit':1}
 a=db('GET','telegram_api_cache',params=params) or [];b=db('GET','telegram_api_cache',params=params) or []
 if digest(a)!=digest(b):raise RuntimeError('Terminal claim changed')
 r['daily_claim']=a
 r['complete']=True
except Exception as exc:r['error']=error(exc)
finally:
 seal('terminal-acceptance',r)
 # Cipher splitting is offline, no private key / plaintext leaves runner.
 p=Path('recovery-output/advertising/daily-advertising-analysis-39015462359.aes.json')
 data=p.read_bytes()
 out=Path('recovery-output/advertising/terminal-cipher-chunks');out.mkdir(exist_ok=True)
 for i in range(0,len(data),2000000):(out/('analysis-'+str(i//2000000).zfill(2)+'.part')).write_bytes(data[i:i+2000000])
 (out/'manifest.json').write_text(json.dumps({'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'parts':(len(data)+1999999)//2000000}))
 print(json.dumps({'complete':r.get('complete',False),'source_calls':0,'db_writes':0,'wb_calls':0,'telegram_calls':0}))
