"""Synthetic loopback PostgreSQL only. No production credentials/transports."""
import os,sys,json,time,hashlib,base64,tempfile,concurrent.futures,statistics,ast,types
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parent
if (ROOT.parent/'pg-signature-isolated/deps').exists():sys.path.insert(0,str(ROOT.parent/'pg-signature-isolated/deps'))
import psycopg
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
DSN=os.getenv('ISOLATED_DSN','host=127.0.0.1 port=55439 user=isolated_test dbname=postgres connect_timeout=5')
assert 'host=127.0.0.1 ' in DSN
shim=types.ModuleType('review_telegram_approval')
shim.sha=lambda v:hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
sys.modules['review_telegram_approval']=shim
backup=types.ModuleType('fixed_backup');exec((ROOT/'source/review_approval_backup.py').read_text(encoding='utf8'),backup.__dict__)
PROFILE={'events':(5629,6598223),'cards':(1070,2037915),'items':(770,91056),'intents':(769,1130792),'source_cache':(2936,5526806)}
SCOPES=[(h,c) for h in ('approval','morning') for c in ('token_1','token_2','token_3')]
SECRET=b'public-synthetic-test-key-not-production'

class Meter:
 def __init__(self,c):self.c=c;self.bytes=0;self.queries=0;self.sql_ms=0
 def transaction(self):return self.c.transaction()
 def execute(self,q,args=()):
  start=time.perf_counter();cur=self.c.execute(q,args);self.sql_ms+=(time.perf_counter()-start)*1000;self.queries+=1;meter=self
  class Result:
   def account(self,rows):
    meter.bytes+=sum(len(json.dumps(row,default=str,ensure_ascii=False).encode()) for row in rows);return rows
   def fetchall(self):return self.account(cur.fetchall())
   def fetchone(self):return self.account([cur.fetchone()])[0]
  return Result()
def repo(m):return SimpleNamespace(pg=True,conn=m,execute=lambda q,args=():m.execute(q.replace('{p}','review_approval.'),args))
def seed(scale):
 with psycopg.connect(DSN,autocommit=True) as c:
  c.execute('drop schema if exists review_approval cascade');c.execute('create schema review_approval')
  for t in backup.TABLES:c.execute('create table review_approval.'+t+'(id text primary key,payload text not null)')
  c.execute('create table review_approval.cache_base(cache_key text primary key,payload jsonb,updated_at timestamptz)')
  c.execute('create view review_approval.source_cache as select * from review_approval.cache_base')
  c.execute('create table review_approval.journal_base(feedback_id text primary key,state text,error text)')
  c.execute('create view review_approval.source_journal as select * from review_approval.journal_base')
  for t,(count,size) in PROFILE.items():
   rows=[]
   for i in range(count*scale):
    n=max(1,size//count-14);s=base64.b64encode(hashlib.shake_256((t+str(i)).encode()).digest(n)).decode()[:n]
    k=('reviews:' if t=='source_cache' else '')+str(i).zfill(8);v=json.dumps({'padding':s},separators=(',',':'))
    rows.append((k,v,'2026-11-13T00:00:00Z') if t=='source_cache' else (k,v))
   with c.cursor() as cur:
    if t=='source_cache':cur.executemany('insert into review_approval.cache_base values (%s,%s::jsonb,%s)',rows)
    else:cur.executemany('insert into review_approval.'+t+' values (%s,%s)',rows)
  c.execute("insert into review_approval.cache_base values ('reviews:null',null,null),('reviews:json-null','null',null)")
  c.execute("insert into review_approval.journal_base select i::text,null,null from generate_series(1,%s) i",(100*scale,))
  c.execute('analyze')
def full_preserve(handler,r,out,public,capture):
 file='review_approval_process.py' if handler=='approval' else 'review_morning.py'
 tree=ast.parse((ROOT/'source'/file).read_text(encoding='utf8'))
 fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='preserve')
 calls=[];state={'synthetic_only':True}
 ns=dict(snapshot=lambda ignored:capture(),encrypt=backup.encrypt,json=json,Path=Path,os=SimpleNamespace(environ={'RUNNER_TEMP':str(out),'RECOVERY_PUBLIC_KEY':public.decode()}),approval=SimpleNamespace(repo=r),repo=r,output=out,OWNER_PUBLIC=public.decode(),state=state,seal=lambda name,value:calls.append((name,value)))
 exec(compile(ast.Module(body=[fn],type_ignores=[]),file,'exec'),ns);ns['preserve']()
 if handler=='morning':assert calls==[('reviews-morning',state)]
 return out/'approval-supplement.aes.json' if handler=='approval' else out/'stock-deploy-proof/morning-live-supplement.aes.json'
def capture(scope,directory,phase,mode='incremental',require=False):
 handler,cabinet=scope;out=Path(directory)/(handler+'-'+cabinet);out.mkdir(parents=True,exist_ok=True)
 cache=out/'state.aes';key=rsa.generate_private_key(public_exponent=65537,key_size=2048);public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
 with psycopg.connect(DSN,autocommit=True) as c:
  m=Meter(c);r=repo(m);b=backup.IncrementalSnapshot(r,cache,SECRET,'isolated-null-v2:'+handler+':'+cabinet)
  if require:assert b.cache_status=='restored',b.cache_status
  start=time.perf_counter();captured=[]
  def get():
   data=backup.snapshot(r) if mode=='full' else b.capture();captured.append(data);return data
  file=full_preserve(handler,r,out,public,get);total_ms=(time.perf_counter()-start)*1000;bytes_read=m.bytes;sql_ms=m.sql_ms;queries=m.queries
  data=backup.decrypt(json.loads(file.read_text()),key);assert data==captured[0]
  expected=backup.snapshot(r);assert data['tables']==expected['tables'];assert data['manifest']==expected['manifest']
  if mode!='full':b.save_cache()
  # Wrong scope must not authenticate. Encrypted cache is the only cached file.
  wrong=backup.IncrementalSnapshot(r,cache,SECRET,'wrong-scope');assert wrong.cache_status=='cold'
  return dict(handler=handler,cabinet=cabinet,phase=phase,cache_status=b.cache_status,response_bytes=bytes_read,sql_ms=round(sql_ms,2),total_ms=round(total_ms,2),queries=queries,cache_file_bytes=cache.stat().st_size if cache.exists() else 0,full_artifact_bytes=file.stat().st_size,manifest_match=True,null_payload_preserved=any(x['cache_key']=='reviews:null' and x['payload'] is None for x in data['tables']['source_cache']))
def load():
 results=[]
 for scale in (1,3):
  seed(scale)
  with tempfile.TemporaryDirectory(dir=ROOT) as directory:
   for workers in (1,6):
    # Independent namespaces for fair cold/restart comparisons.
    target=Path(directory)/str(workers)
    for phase in ('full','cold','restored','restored-repeat'):
     with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
      records=list(pool.map(lambda s:capture(s,target,phase,'full' if phase=='full' else 'incremental',require=phase.startswith('restored')),SCOPES))
     results.extend(dict(x,scale=scale,clients=workers) for x in records)
     print(json.dumps({'scale':scale,'clients':workers,'phase':phase,'all6_manifest_match':all(x['manifest_match'] for x in records),'median_total_ms':statistics.median(x['total_ms'] for x in records)}),flush=True)
  with psycopg.connect(DSN,autocommit=True) as c:print('TEMP_STATS',c.execute('select temp_files,temp_bytes from pg_stat_database where datname=current_database()').fetchone(),flush=True)
 (ROOT/'load-results.json').write_text(json.dumps(results,indent=2),encoding='utf8')
def transport(mode,handler,cabinet):
 seed(1);directory=Path(os.getenv('TEST_CACHE_DIR',str(ROOT/'transport-cache')))
 exists=(directory/(handler+'-'+cabinet)/'state.aes').exists()
 record=capture((handler,cabinet),directory,mode,require=mode=='restore' or bool(os.getenv('MATCHED_KEY')))
 record.update(mode=mode,prior_cache_present=exists,matched_key=os.getenv('MATCHED_KEY',''),run_id=os.getenv('GITHUB_RUN_ID','local'))
 (ROOT/('transport-'+mode+'-'+handler+'-'+cabinet+'.json')).write_text(json.dumps(record,indent=2),encoding='utf8')
 print('TRANSPORT_RESULT '+json.dumps(record),flush=True)
if __name__=='__main__':
 if sys.argv[1]=='load':load()
 else:transport(*sys.argv[1:4])

