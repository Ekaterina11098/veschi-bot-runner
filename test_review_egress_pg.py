"""Real isolated Postgres regression; never accepts a production database DSN."""
import contextlib,json,os,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
import psycopg
from psycopg.types.json import Jsonb
from review_telegram_approval import Repository,Approval,sha
from review_approval_backup import snapshot,IncrementalSnapshot,validate,encrypt,decrypt
from review_approved_worker import due_intents
from review_approval_cleanup import cleanup_completed
from review_approved_benchmarks import sync,sync_live
from test_review_approved_benchmarks import Tests as BenchmarkCases
from test_review_cleanup import CleanupTests

class Cursor:
    def __init__(self,c,owner):self.c=c;self.owner=owner
    def fetchall(self):
        rows=self.c.fetchall();self.owner.bytes+=len(json.dumps(rows,default=str).encode());return rows
    def fetchone(self):
        row=self.c.fetchone();self.owner.bytes+=len(json.dumps(row,default=str).encode());return row

class MeasuredConnection:
    def __init__(self,c):self.c=c;self.bytes=0;self.fail=False
    def transaction(self):return self.c.transaction()
    def execute(self,sql,args=()):
        if self.fail and sql.startswith('SELECT events'):raise RuntimeError('Injected read failure')
        return Cursor(self.c.execute(sql,args),self)

class EgressPGTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn=psycopg.connect(os.environ['EGRESS_TEST_DSN'],autocommit=True)
        db,host=cls.conn.execute('select current_database(),inet_server_addr()::text').fetchone()
        if db!='review_egress_test' or host not in ('127.0.0.1','::1',None):raise RuntimeError('Isolated test database only')
        cls.conn.execute('CREATE SCHEMA review_approval')
        for name in ('items','cards','events','intents'):
            cls.conn.execute('CREATE TABLE review_approval.'+name+'(id text primary key,payload text not null)')
        cls.conn.execute('CREATE TABLE review_approval.cache_data(cache_key text primary key,payload jsonb,updated_at timestamptz default now())')
        cls.conn.execute('CREATE TABLE review_approval.journal_data(feedback_id text primary key,state text,error text)')
        cls.conn.execute('CREATE VIEW review_approval.source_cache AS SELECT * FROM review_approval.cache_data')
        cls.conn.execute('CREATE VIEW review_approval.source_journal AS SELECT * FROM review_approval.journal_data')
    @classmethod
    def tearDownClass(cls):cls.conn.close()
    def setUp(self):
        self.conn.execute('SET search_path=review_approval,public')
        self.conn.execute('TRUNCATE review_approval.items,review_approval.cards,review_approval.events,review_approval.intents,review_approval.cache_data,review_approval.journal_data')
        self.repo=Repository(self.conn,postgres=True)
        self.measured=MeasuredConnection(self.conn);self.repo.conn=self.measured
    def seed(self):
        for n in range(150):
            self.repo.put('events','event:'+str(n),dict(text='history'*2000,n=n))
        self.conn.execute('INSERT INTO review_approval.cache_data(cache_key,payload) VALUES(%s,%s)',('reviews:test',Jsonb({'large':'x'*20000})))
        self.conn.execute("INSERT INTO review_approval.journal_data VALUES('review','pending',NULL)")
    def test_full_backup_compatible_and_idle_capture_under_one_percent(self):
        self.seed();b=IncrementalSnapshot(self.repo)
        first=b.capture();baseline=self.measured.bytes
        old=snapshot(self.repo)
        self.assertEqual(first['tables'],old['tables']);self.assertEqual(first['manifest'],old['manifest'])
        self.measured.bytes=0;again=b.capture()
        self.assertEqual(first['tables'],again['tables'])
        self.assertLess(self.measured.bytes,baseline/100)
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        self.assertEqual(decrypt(encrypt(again,public),key)['tables'],first['tables'])
        print('BACKUP idle bytes',self.measured.bytes,'initial bytes',baseline)
    def test_changes_deletes_and_view_updates_are_not_skipped(self):
        self.seed();b=IncrementalSnapshot(self.repo);b.capture();self.measured.bytes=0
        self.repo.put('events','event:1',{'new':'changed'})
        self.conn.execute("DELETE FROM review_approval.events WHERE id='event:2'")
        self.conn.execute("UPDATE review_approval.cache_data SET payload='{}'")
        self.conn.execute("UPDATE review_approval.journal_data SET state='sent',error='changed'")
        new=b.capture();self.assertEqual(new['tables'],snapshot(self.repo)['tables'])
        validate(new)
    def test_pending_selector_matches_legacy_across_retries_chats_and_cutover(self):
        cfg=dict(owner_id='owner',chat_id='private',content_group_chat_id='group',cutover=50)
        for n in range(90):
            self.repo.put('intents',str(n),dict(id=str(n),cabinet=('token_1','token_2','token_3')[n%3],status=('confirmed','awaiting_preflight','verify')[n%3],created_at=n+10,owner_id='owner' if n%5 else 'other',chat_id='group' if n%2 else 'private',retry_at=2000 if n%7==0 else 0,worker_retry_at=2000 if n%11==0 else 0,verification_empty_at=20 if n%13==0 else None))
        for cab in (None,'token_1','token_2','token_3'):
            for now in (1000,float('inf')):
                self.repo.pg=False;expected=due_intents(self.repo,cfg,cab,now);self.repo.pg=True
                self.assertEqual(due_intents(self.repo,cfg,cab,now),expected)
    def test_benchmark_filtered_reader_matches_legacy_and_saves_nothing_twice(self):
        cards,events,intents=BenchmarkCases().case()
        for table,data in [('cards',cards),('events',events),('intents',intents)]:
            for k,v in data.items():self.repo.put(table,k,v)
        for n in range(100):self.repo.put('events','health:'+str(n),{'large':'x'*10000})
        saved={};writes=[]
        def write(row):saved[row['feedback_id']]=row;writes.append(row)
        result=sync(self.repo,'owner',write,saved.get)
        self.assertEqual(result['saved'],1);self.assertEqual(len(writes),1)
        self.assertEqual(sync(self.repo,'owner',write,saved.get)['existing'],1)
        self.assertEqual(len(writes),1)
    def test_live_signature_ignores_health_but_detects_new_revision(self):
        env={'SUPABASE_URL':'https://unused.example','SUPABASE_SECRET_KEY':'synthetic'}
        with patch.dict(os.environ,env),patch('review_approved_benchmarks.sync',return_value={'errors':0,'saved':0}) as call:
            sync_live(self.repo,'owner');self.assertEqual(call.call_count,1)
            self.repo.put('events','approved-worker:health:v1',{'checked_at':1})
            self.assertTrue(sync_live(self.repo,'owner')['unchanged']);self.assertEqual(call.call_count,1)
            self.repo.put('events','edit:new',{'decision':'revision_requested'})
            sync_live(self.repo,'owner');self.assertEqual(call.call_count,2)
    def test_filtered_cleanup_same_exact_targets_without_touching_other_reviews(self):
        helper=CleanupTests();old,tg,i=helper.setup_case(state='awaiting_preflight')
        card=dict(old.repo.get('cards','c'),message_id=11)
        old.repo.put('cards','old',card);old.repo.put('events','edit:old',{'token':'old'})
        old.repo.put('events','revision-delivery:old',{'revision_event_id':'edit:old','message_id':12})
        old.repo.conn.commit()
        for table in ('items','cards','events','intents'):
            for k,raw in old.repo.execute('SELECT id,payload FROM {p}'+table).fetchall():self.repo.put(table,k,json.loads(raw))
        expected=cleanup_completed(old,tg,intent_id='i');targets={c.args[1]['message_id'] for c in tg.call.call_args_list}
        a=Approval(self.repo,'s','owner','chat','bot',clock=lambda:1000);actual_tg=Mock();actual_tg.call.return_value=True
        result=cleanup_completed(a,actual_tg,intent_id='i')
        self.assertEqual(result,expected);self.assertEqual({c.args[1]['message_id'] for c in actual_tg.call.call_args_list},targets)
        self.assertEqual(self.repo.get('cards','unprocessed')['message_id'],99)
        cleanup_completed(a,actual_tg,intent_id='i');self.assertEqual(actual_tg.call.call_count,len(targets))

if __name__=='__main__':unittest.main()
