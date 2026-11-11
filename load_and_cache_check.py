"""Synthetic load / GitHub cache transport tests. Loopback PostgreSQL only."""
import sys,os,json,time,hashlib,base64,statistics,concurrent.futures,socket,argparse
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).parent
sys.path[:0]=[str(ROOT/'deps'),str(ROOT/'source/review-approval-preparation')]
import psycopg
import candidate_backup as candidate
import review_approval_backup as original
from review_telegram_approval import Repository
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
PROFILE=json.loads((ROOT/'production_profile.json').read_text())
DSN=os.getenv('ISOLATED_DSN','host=127.0.0.1 port=55439 user=isolated_test dbname=postgres connect_timeout=3')
if '127.0.0.1' not in DSN:raise RuntimeError('Loopback required')
def conn():return psycopg.connect(DSN,autocommit=True)
def padding(seed,length):
    return base64.b64encode(hashlib.shake_256(seed.encode()).digest(length)).decode()[:length]
def seed(scale=1):
    with conn() as c:
        r=Repository(c,postgres=True);c.execute('drop schema if exists review_approval cascade');r.setup()
        c.execute('create table review_approval.cache_base(cache_key text primary key,payload jsonb,updated_at timestamptz)')
        c.execute('create view review_approval.source_cache as select * from review_approval.cache_base')
        c.execute('create table review_approval.journal_base(feedback_id text primary key,state text,error text)')
        c.execute('create view review_approval.source_journal as select * from review_approval.journal_base')
        for spec in PROFILE['tables']:
            t=spec['t'];n=spec['n']*scale;total=spec['bytes']*scale;largest=spec['max_bytes']
            lengths=[largest]+[(total-largest)//(n-1)]*(n-1)
            for i in range((total-largest)%(n-1)):lengths[i+1]+=1
            keylen=max(12,spec['key_bytes']//spec['n'])
            rows=[]
            for i,length in enumerate(lengths):
                k=(('reviews:' if t=='source_cache' else '')+str(i).zfill(8)).ljust(keylen,'k')
                value=json.dumps({'padding':padding(t+str(i),max(0,length-15))},separators=(',',':'))
                if t=='source_cache':rows.append((k,value,'2026-11-11T00:00:00Z'))
                elif t=='source_journal':rows.append((k,None,padding(t+str(i),length)))
                else:rows.append((k,value))
            with c.cursor() as cur:
                if t=='source_cache':cur.executemany('insert into review_approval.cache_base values (%s,%s::jsonb,%s)',rows)
                elif t=='source_journal':cur.executemany('insert into review_approval.journal_base values (%s,%s,%s)',rows)
                else:cur.executemany('insert into review_approval.'+t+' values (%s,%s)',rows)
        c.execute('analyze')
    return {'rows':sum(s['n']*scale for s in PROFILE['tables']),'payload_bytes_target':sum(s['bytes']*scale for s in PROFILE['tables'])}
class Meter:
    def __init__(self,c):self.c=c;self.bytes=0;self.queries=0;self.sql_ms=0;self.signatures_ms=0
    def transaction(self):return self.c.transaction()
    def execute(self,q,args=()):
        start=time.perf_counter();cursor=self.c.execute(q,args);elapsed=(time.perf_counter()-start)*1000
        self.sql_ms+=elapsed;self.queries+=1
        if "'server-signature-v2'" in q:self.signatures_ms+=elapsed
        meter=self
        class Cursor:
            def account(self,rows):
                for row in rows:
                    meter.bytes+=7+4*len(row)+sum(len((json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else str(v)).encode()) for v in row if v is not None)
                return rows
            def fetchall(self):return self.account(cursor.fetchall())
            def fetchone(self):
                row=cursor.fetchone();return self.account([row])[0] if row is not None else None
        return Cursor()
def capture(cabinet,implementation,phase,public=None):
    path=ROOT/'load-cache'/implementation/cabinet/'state.aes';path.parent.mkdir(parents=True,exist_ok=True)
    module=candidate if implementation=='candidate' else original
    with conn() as c:
        meter=Meter(c);repo=SimpleNamespace(pg=True,conn=meter)
        begin=time.perf_counter();b=module.IncrementalSnapshot(repo,path,b'synthetic-only-test-key','isolated:'+cabinet);load_ms=(time.perf_counter()-begin)*1000
        begin=time.perf_counter();data=b.capture();capture_ms=(time.perf_counter()-begin)*1000
        begin=time.perf_counter();b.save_cache();save_ms=(time.perf_counter()-begin)*1000
        encryption_ms=None
        if public:
            begin=time.perf_counter();candidate.encrypt(data,public);encryption_ms=(time.perf_counter()-begin)*1000
        return dict(cabinet=cabinet,implementation=implementation,phase=phase,cache_status=b.cache_status,load_ms=load_ms,capture_ms=capture_ms,save_ms=save_ms,full_encrypt_ms=encryption_ms,sql_ms=meter.sql_ms,signatures_ms=meter.signatures_ms,estimated_data_row_bytes=meter.bytes,queries=meter.queries,cache_bytes=path.stat().st_size,manifest=data['manifest'])
def load_test(scale):
    size=seed(scale)
    for implementation in ('original','candidate'):
        for cabinet in ('token_1','token_2','token_3'):(ROOT/'load-cache'/implementation/cabinet).mkdir(parents=True,exist_ok=True)
    for p in (ROOT/'load-cache').glob('*/*/state.aes'):p.unlink()
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    results=[]
    for impl in ('original','candidate'):
        for phase in ('cold','unchanged-1','unchanged-2','unchanged-3'):
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                records=list(pool.map(lambda cabinet:capture(cabinet,impl,phase,public),('token_1','token_2','token_3')))
            results+=records
            assert all(x['manifest']==records[0]['manifest'] for x in records)
        with conn() as c:c.execute("update review_approval.events set payload=payload||' ' where id in (select id from review_approval.events order by id limit 10)")
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results+=list(pool.map(lambda cabinet:capture(cabinet,impl,'changed-10-events',public),('token_1','token_2','token_3')))
        # Restore identical source before comparing the other implementation.
        seed(scale)
    summary={}
    for impl in ('original','candidate'):
        warm=[r for r in results if r['implementation']==impl and r['phase'].startswith('unchanged')]
        summary[impl]={k:statistics.median(r[k] for r in warm) for k in ('load_ms','capture_ms','save_ms','full_encrypt_ms','sql_ms','signatures_ms','estimated_data_row_bytes','cache_bytes')}
    result=dict(scale=scale,size=size,summary=summary,records=results,note='Synthetic aggregate-matched data; 3 concurrent independent clients; local wall time, not Supabase CPU or provider billing. Byte count estimates DataRow payload/protocol, excludes TLS/other protocol frames.')
    (ROOT/f'load-results-{scale}x.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({'scale':scale,'size':size,'summary':summary}))
def cache_check(mode,cabinet):
    seed();path=Path(os.environ['TEST_CACHE_DIR']);path.mkdir(parents=True,exist_ok=True);cache=path/'state.aes'
    with conn() as c:
        meter=Meter(c);repo=SimpleNamespace(pg=True,conn=meter)
        b=candidate.IncrementalSnapshot(repo,cache,b'public-synthetic-key-not-a-secret','isolated:'+cabinet)
        if mode=='restore':
            assert b.cache_status=='restored','Encrypted state not restored'
            expected=json.loads((path/'expected.json').read_text());assert hashlib.sha256(cache.read_bytes()).hexdigest()==expected['file_sha256']
            data=b.capture();assert data['manifest']==expected['manifest']
            # 6 signatures + point produce a tiny response; no versions/payload lists allowed.
            assert meter.queries==8 and meter.bytes<4096,(meter.queries,meter.bytes)
            for other in ('token_1','token_2','token_3'):
                if other!=cabinet:assert candidate.IncrementalSnapshot(repo,cache,b'public-synthetic-key-not-a-secret','isolated:'+other).cache_status=='cold'
        else:
            data=b.capture();b.save_cache();(path/'expected.json').write_text(json.dumps({'manifest':data['manifest'],'file_sha256':hashlib.sha256(cache.read_bytes()).hexdigest()}))
        result={'mode':mode,'cabinet':cabinet,'cache_status':b.cache_status,'bytes':meter.bytes,'queries':meter.queries,'cache_file_bytes':cache.stat().st_size,'manifest_match':True}
        print(json.dumps(result))
        (ROOT/f'cache-result-{mode}-{cabinet}.json').write_text(json.dumps(result,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['load','seed','restore']);p.add_argument('--scale',type=int,default=1);p.add_argument('--cabinet',default='token_1');a=p.parse_args()
    if a.mode=='load':load_test(a.scale)
    else:cache_check(a.mode,a.cabinet)
