"""Real PostgreSQL tests. Requires explicitly isolated Unix-socket DSN, no source credentials."""
import copy,json,os,unittest
import psycopg
from psycopg.types.json import Jsonb
from pathlib import Path
from review_telegram_approval import Approval,Repository,Rejected,sha
from review_approval_bridge import SQLSource,DurableBridge
from review_telegram_runtime import CanonicalGuard
from review_telegram_receiver import Receiver
from review_approval_executor import Executor,ExplicitRateLimit
from review_approval_backup import snapshot,encrypt,decrypt,restore_empty

class Crash(BaseException):pass
class WB:
    def __init__(self):self.answer='';self.posts=0;self.reads=0;self.paused=0;self.mode='ok'
    def pause(self,cabinet):return self.paused
    def read(self,intent):self.reads+=1;return self.answer
    def post(self,intent):
        self.posts+=1
        if self.mode=='429':raise ExplicitRateLimit(60)
        if self.mode=='unknown-empty':raise TimeoutError()
        self.answer=intent['answer']
        if self.mode=='crash':raise Crash()
        if self.mode=='unknown-accepted':raise TimeoutError()
class TG:
    def __init__(self):self.calls=[]
    def call(self,m,p):self.calls.append(m);return True

class PostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dsn=os.environ['TEST_DSN']
        cls.admin=psycopg.connect(dsn,autocommit=True)
        db,ip=cls.admin.execute('SELECT current_database(),inet_server_addr()').fetchone()
        assert db=='review_approval_test' and ip is None,'Only isolated Unix-socket test database permitted'
        cls.admin.execute('CREATE TABLE IF NOT EXISTS public.telegram_api_cache(cache_key text primary key,payload jsonb not null,updated_at timestamptz not null default now())')
        cls.admin.execute('CREATE TABLE IF NOT EXISTS public.review_replies(feedback_id text primary key,state text,error text)')
        cls.admin.execute(Path('schema-proposal.sql').read_text(encoding='utf-8-sig'))
    @classmethod
    def tearDownClass(cls):cls.admin.close()
    def setUp(self):
        self.admin.execute('TRUNCATE review_approval.items,review_approval.cards,review_approval.events,review_approval.intents,public.telegram_api_cache,public.review_replies')
        self.conn=psycopg.connect(os.environ['TEST_DSN'],autocommit=True)
        self.conn.execute('SET ROLE review_approval_runtime')
        self.repo=Repository(self.conn,postgres=True);self.now=1000
        self.a=Approval(self.repo,'secret',11,22,33,enabled=True,clock=lambda:self.now)
        self.bridge=DurableBridge(self.a,SQLSource(self.conn));self.guard=CanonicalGuard(self.a,self.bridge.project)
        self.wb=WB();self.executor=Executor(self.a,self.guard,self.wb,enabled=True)
        self.item=dict(id='synthetic-review',userName='Тест',productValuation=4,text='Выбрала другую модель',pros='',cons='',productDetails={'supplierArticle':'SYNTHETIC-ARTICLE'})
        self.version='test-v1';self.variants=['Тест, добрый день. Спасибо за отзыв!','Тест, добрый день. Благодарим за впечатления!']
        self.seed(self.item,'token_1',self.version)
        self.token,_=self.bridge.create(self.item,'token_1','feedbacks',self.version,101)
    def tearDown(self):self.conn.close()
    def seed(self,item,cabinet,version):
        key=self.bridge.draft_key(cabinet,'feedbacks',item['id'],version)
        payload=dict(cabinet=cabinet,kind='feedbacks',item_id=item['id'],version=version,source_sha256=sha(item),variants=self.variants,confirmation_status='draft')
        self.admin.execute('INSERT INTO public.telegram_api_cache(cache_key,payload) VALUES (%s,%s) ON CONFLICT(cache_key) DO UPDATE SET payload=excluded.payload,updated_at=clock_timestamp()',(key,Jsonb(payload)))
    def update(self,action,event):
        return {'callback_query':{'id':event,'from':{'id':11},'data':'rv1:'+self.token+':'+action,'message':{'message_id':101,'chat':{'id':22,'type':'private'},'from':{'id':33}}}}
    def approve(self):
        receiver=Receiver(self.a,TG(),self.guard)
        receiver.receive(self.update('v2','select'),'secret')
        nonce=self.repo.get('cards',self.token)['nonce']
        return receiver.receive(self.update('ok.'+nonce,'confirm'),'secret')['result']['intent_id']
    def test_full_path_actual_postgres(self):
        intent=self.approve();result=self.executor.run(intent)
        self.assertEqual(result['status'],'confirmed');self.assertEqual(self.wb.posts,1);self.assertEqual(self.wb.reads,2)
        self.assertEqual(self.repo.get('intents',intent)['answer'],self.variants[1])
        self.executor.run(intent);self.assertEqual(self.wb.posts,1)
    def test_unknown_accepted_get_only(self):
        intent=self.approve();self.wb.mode='unknown-accepted';self.assertEqual(self.executor.run(intent)['status'],'verify')
        self.assertEqual(self.executor.run(intent)['status'],'confirmed');self.assertEqual(self.wb.posts,1)
    def test_unknown_empty_get_only(self):
        intent=self.approve();self.wb.mode='unknown-empty';self.executor.run(intent)
        self.assertEqual(self.executor.run(intent)['status'],'verify');self.assertEqual(self.wb.posts,1)
    def test_crash_after_wb_before_confirm(self):
        intent=self.approve();self.wb.mode='crash'
        with self.assertRaises(Crash):self.executor.run(intent)
        self.assertEqual(self.repo.get('intents',intent)['status'],'verify')
        self.assertEqual(self.executor.run(intent)['status'],'confirmed');self.assertEqual(self.wb.posts,1)
    def test_429_pause_no_early_retry(self):
        intent=self.approve();self.wb.mode='429';result=self.executor.run(intent)
        self.assertEqual(result['status'],'awaiting_preflight');self.executor.run(intent);self.assertEqual(self.wb.posts,1)
        self.now+=61;self.wb.mode='ok';self.assertEqual(self.executor.run(intent)['status'],'confirmed');self.assertEqual(self.wb.posts,2)
    def test_manual_answer_no_post(self):
        intent=self.approve();self.wb.answer='Владелец ответил вручную'
        self.assertEqual(self.executor.run(intent)['status'],'manual_present');self.assertEqual(self.wb.posts,0)
    def test_new_hold_after_approval(self):
        intent=self.approve();self.admin.execute('INSERT INTO public.telegram_api_cache(cache_key,payload) VALUES(%s,%s)',('reviews:hold:token_1:feedbacks:synthetic-review',Jsonb({'active':True})))
        self.assertEqual(self.executor.run(intent)['status'],'blocked');self.assertEqual(self.wb.posts,0)
    def test_new_version_after_approval(self):
        intent=self.approve();self.seed(self.item,'token_1','test-v2')
        self.assertEqual(self.executor.run(intent)['status'],'blocked');self.assertEqual(self.wb.posts,0)
    def test_old_pending_blocks_without_mutation(self):
        self.admin.execute("INSERT INTO public.review_replies VALUES('synthetic-review','pending','old')")
        with self.assertRaises(Rejected):self.approve()
        self.assertEqual(self.admin.execute('SELECT state,error FROM public.review_replies').fetchone(),('pending','old'))
    def test_old_publication_unknown_blocks(self):
        self.admin.execute('INSERT INTO public.telegram_api_cache(cache_key,payload) VALUES(%s,%s)',('reviews:publication:token_1:synthetic-review:old',Jsonb({'phase':'verify'})))
        with self.assertRaises(Rejected):self.approve()
    def test_ishkhan_hold(self):
        item=dict(self.item,id='PwB5eXmFztbgyBhGctsP');self.seed(item,'token_2','v1')
        self.admin.execute('INSERT INTO public.telegram_api_cache(cache_key,payload) VALUES(%s,%s)',('reviews:hold:token_2:feedbacks:PwB5eXmFztbgyBhGctsP',Jsonb({'active':True})))
        with self.assertRaises(Rejected):self.bridge.create(item,'token_2','feedbacks','v1',102)
        self.approve() # OOO independent.
    def test_runtime_no_old_queue_write(self):
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):self.conn.execute("INSERT INTO public.review_replies VALUES('x','pending','')")
    def test_runtime_no_base_cache_read(self):
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):self.conn.execute('SELECT * FROM public.telegram_api_cache')
    def test_runtime_no_unrelated_cache_read(self):
        self.admin.execute("INSERT INTO public.telegram_api_cache(cache_key,payload) VALUES('other:secret','{}')")
        self.assertEqual(self.conn.execute("SELECT count(*) FROM review_approval.source_cache WHERE cache_key='other:secret'").fetchone()[0],0)
    def test_runtime_no_schema_create(self):
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):self.conn.execute('CREATE TABLE review_approval.unapproved(id int)')
    def test_runtime_no_view_write_after_repeat_schema(self):
        self.admin.execute(Path('schema-proposal.sql').read_text(encoding='utf-8-sig'))
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):self.conn.execute("UPDATE review_approval.source_journal SET state='sent'")
    def test_process_callback_to_publication_and_backup(self):
        from review_approval_process import process
        backups=[];tg=TG()
        def preserve():backups.append(snapshot(self.repo))
        process(self.a,self.bridge,tg,self.wb,self.update('v2','select'),True,preserve)
        nonce=self.repo.get('cards',self.token)['nonce']
        result=process(self.a,self.bridge,tg,self.wb,self.update('ok.'+nonce,'confirm'),True,preserve)
        self.assertEqual(result['publication_status'],'confirmed');self.assertEqual(self.wb.posts,1)
        self.assertEqual(len(backups),4)
        self.assertEqual(backups[2]['tables']['intents'][0]['payload']['status'],'awaiting_preflight')
        self.assertEqual(backups[3]['tables']['intents'][0]['payload']['status'],'confirmed')
    def test_confirm_save_failure_get_only(self):
        intent=self.approve();original=self.executor.save
        def save(value,status,**extra):
            if status=='confirmed':raise RuntimeError('Simulated database save outage')
            return original(value,status,**extra)
        self.executor.save=save
        with self.assertRaises(RuntimeError):self.executor.run(intent)
        self.executor.save=original
        self.assertEqual(self.executor.run(intent)['status'],'confirmed');self.assertEqual(self.wb.posts,1)
    def test_new_notice_create_buttons_and_no_replay(self):
        from review_approval_notice import NewNotice
        # Use a different new review; setUp card is not resent.
        item=dict(self.item,id='new-review');self.seed(item,'token_1','v1')
        calls=[]
        class Telegram:
            def call(inner,method,payload):
                calls.append(method)
                return {'getMe':{'id':33},'getChat':{'id':22,'type':'private'},'sendMessage':{'message_id':202,'chat':{'id':22},'from':{'id':33}},'editMessageText':True}[method]
        notifier=NewNotice(self.a,self.bridge,Telegram(),enabled=True)
        result=notifier.deliver(item,'token_1','feedbacks','v1',1100,1000)
        self.assertEqual(result['buttons'],'confirmed');self.assertEqual(self.repo.get('cards',result['card_token'])['message_id'],202)
        self.assertEqual(notifier.deliver(item,'token_1','feedbacks','v1',1100,1000)['status'],'blocked_existing_delivery')
        self.assertEqual(calls.count('sendMessage'),1)
    def test_unknown_new_notice_never_resends(self):
        from review_approval_notice import NewNotice
        item=dict(self.item,id='new-unknown');self.seed(item,'token_1','v1');calls=[]
        class Telegram:
            def call(inner,method,payload):
                calls.append(method)
                if method=='sendMessage':raise TimeoutError()
                return {'id':33} if method=='getMe' else {'id':22,'type':'private'}
        notifier=NewNotice(self.a,self.bridge,Telegram(),enabled=True)
        self.assertEqual(notifier.deliver(item,'token_1','feedbacks','v1',1100,1000)['status'],'uncertain')
        notifier.deliver(item,'token_1','feedbacks','v1',1100,1000);self.assertEqual(calls.count('sendMessage'),1)
    def test_old_notice_excluded(self):
        from review_approval_notice import NewNotice
        self.admin.execute('INSERT INTO public.telegram_api_cache(cache_key,payload) VALUES(%s,%s)',('reviews:notice:old',Jsonb({'scope':'old-batch:token_1:synthetic-review','status':'confirmed'})))
        with self.assertRaises(Rejected):NewNotice(self.a,self.bridge,TG(),enabled=True).deliver(self.item,'token_1','feedbacks',self.version,1100,1000)
    def test_pg_competing_executor_lock(self):
        intent=self.approve();other=psycopg.connect(os.environ['TEST_DSN'],autocommit=True)
        try:
            other.execute('SELECT pg_advisory_lock(hashtextextended(%s,0))',('review-approval:'+intent,))
            self.assertTrue(self.executor.run(intent)['busy']);self.assertEqual(self.wb.posts,0)
        finally:other.close()
    def test_pg_concurrent_confirmations(self):
        import concurrent.futures
        self.a.handle(self.update('v1','select'),'secret');nonce=self.repo.get('cards',self.token)['nonce']
        def click(event):
            conn=psycopg.connect(os.environ['TEST_DSN'],autocommit=True)
            try:
                app=Approval(Repository(conn,postgres=True),'secret',11,22,33,enabled=True,clock=lambda:self.now)
                try:app.handle(self.update('ok.'+nonce,event),'secret');return 'approved'
                except Rejected:return 'rejected'
            finally:conn.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(click,['c1','c2']))
        self.assertEqual(sorted(results),['approved','rejected']);self.assertEqual(self.repo.count('intents'),1)
    def test_pg_same_callback_id_different_reviews(self):
        import concurrent.futures
        token2,_=self.a.create('token_2','feedbacks','other','v1',self.a.repo.get('cards',self.token)['source'],['A','B'],102)
        def click(pair):
            token,message=pair;conn=psycopg.connect(os.environ['TEST_DSN'],autocommit=True)
            try:
                app=Approval(Repository(conn,postgres=True),'secret',11,22,33,enabled=True,clock=lambda:self.now)
                update=self.update('v1','shared-event');update['callback_query']['data']='rv1:'+token+':v1';update['callback_query']['message']['message_id']=message
                try:app.handle(update,'secret');return 'selected'
                except Rejected:return 'rejected'
            finally:conn.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(click,[(self.token,101),(token2,102)]))
        self.assertEqual(sorted(results),['rejected','selected']);self.assertEqual(self.repo.count('events'),1)
    def test_backup_encrypt_restore_and_resume(self):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        intent=self.approve();self.wb.mode='unknown-accepted';self.executor.run(intent)
        held,_=self.a.create('token_2','questions','held-review','v1',self.repo.get('cards',self.token)['source'],['A','B'],102)
        self.a.set_item_state(self.repo.get('cards',held)['ref'],'held','owner instruction')
        revision,_=self.a.create('token_3','questions','edit-review','v1',self.repo.get('cards',self.token)['source'],['A','B'],103)
        update=self.update('edit','edit-event');update['callback_query']['data']='rv1:'+revision+':edit';update['callback_query']['message']['message_id']=103
        self.a.handle(update,'secret');self.a.record_edit(revision,11,22,103,'Уточнить исходный отзыв')
        self.admin.execute("INSERT INTO public.review_replies VALUES('old-sent','sent','manual'),('old-pending','pending','old'),('old-unknown','needs_check','uncertain')")
        data=snapshot(self.repo)
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        pem=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        envelope=encrypt(data,pem);decoded=decrypt(json.loads(json.dumps(envelope)),key)
        # Restore to a separate database; source rows are from the encrypted supplement.
        self.admin.execute('DROP DATABASE IF EXISTS review_approval_restore WITH (FORCE)')
        self.admin.execute('CREATE DATABASE review_approval_restore')
        restore=psycopg.connect(os.environ['TEST_DSN'].replace('dbname=review_approval_test','dbname=review_approval_restore'),autocommit=True)
        try:
            restore.execute('CREATE TABLE public.telegram_api_cache(cache_key text primary key,payload jsonb,updated_at timestamptz)')
            restore.execute('CREATE TABLE public.review_replies(feedback_id text primary key,state text,error text)')
            restore.execute(Path('schema-proposal.sql').read_text(encoding='utf-8-sig'))
            for row in decoded['tables']['source_cache']:restore.execute('INSERT INTO public.telegram_api_cache VALUES(%s,%s,%s)',(row['cache_key'],Jsonb(row['payload']),row['updated_at']))
            for row in decoded['tables']['source_journal']:restore.execute('INSERT INTO public.review_replies VALUES(%s,%s,%s)',(row['feedback_id'],row['state'],row['error']))
            repo=Repository(restore,postgres=True);self.assertTrue(restore_empty(repo,decoded))
            self.assertEqual(repo.get('items',self.repo.get('cards',held)['ref'])['status'],'held')
            self.assertEqual(repo.get('cards',revision)['status'],'rework')
            self.assertEqual({x['state'] for x in decoded['tables']['source_journal']},{'sent','pending','needs_check'})
            app=Approval(repo,'secret',11,22,33,enabled=True,clock=lambda:self.now)
            bridge=DurableBridge(app,SQLSource(restore))
            executor=Executor(app,CanonicalGuard(app,bridge.project),self.wb,enabled=True)
            self.assertEqual(executor.run(intent)['status'],'confirmed');self.assertEqual(self.wb.posts,1)
            corrupt=copy.deepcopy(envelope);corrupt['plaintext_sha256']='0'*64
            with self.assertRaises(ValueError):decrypt(corrupt,key)
            import base64
            from cryptography.exceptions import InvalidTag
            corrupt=copy.deepcopy(envelope);cipher=bytearray(base64.b64decode(corrupt['ciphertext']));cipher[-1]^=1;corrupt['ciphertext']=base64.b64encode(cipher).decode()
            with self.assertRaises(InvalidTag):decrypt(corrupt,key)
        finally:restore.close()

if __name__=='__main__':unittest.main(verbosity=2)

