import unittest,sqlite3,copy
from types import SimpleNamespace
from unittest.mock import patch
import review_646_controlled_retry as m
from review_telegram_approval import Repository,sha,Rejected

class Tests(unittest.TestCase):
    def setUp(self):
        self.conn=sqlite3.connect(':memory:');self.repo=Repository(self.conn);self.repo.setup();self.now=1000
        self.answer='Exact approved test text';self.ref='test-ref'
        self.hash=sha(self.answer);self.hp=patch.object(m,'ANSWER',self.hash);self.hp.start();self.addCleanup(self.hp.stop)
        self.i=dict(id=m.INTENT,cabinet='token_1',kind='feedbacks',item_id=m.ITEM,version=m.VERSION,
            card_token=m.CARD,answer=self.answer,answer_sha256=self.hash,status='verify',ref=self.ref,owner_id='owner',chat_id='chat',source_sha256=sha({'text':'source'}))
        self.c=dict(cabinet='token_1',kind='feedbacks',item_id=m.ITEM,version=m.VERSION,message_id=646,hashes=[self.hash],ref=self.ref,source={'text':'source'},texts=[self.answer])
        self.repo.put('intents',m.INTENT,self.i);self.repo.put('cards',m.CARD,self.c);self.repo.put('items',self.ref,dict(status='uncertain'));self.conn.commit()
        self.wb=SimpleNamespace(pause=lambda cabinet:0,read=self.read,post=self.post)
        self.reads=0;self.posts=0;self.actual='';self.response=204;self.timeout=False
        self.r=m.Retry(SimpleNamespace(repo=self.repo,owner='owner',chat='chat'),self.wb,lambda card:True,clock=lambda:self.now)
    def read(self,intent):self.reads+=1;return self.actual
    def post(self,intent):
        self.posts+=1
        assert self.r.operation()['post_consumed']
        if self.timeout:raise TimeoutError()
        self.r.record(dict(method='POST',phase='after_http',http_status=self.response,application_error=False))
        if self.response>=400:raise RuntimeError('rejected')
    def ready(self):
        self.r.step();self.now+=m.BURST_GAP
    def test_original_uncertain_history_retained(self):
        op=self.r.initialize();self.assertEqual(op['original_unknown_attempt'],self.i)
        self.assertEqual(self.repo.get('intents',m.INTENT)['status'],'verify')
    def test_existing_answer_no_post(self):
        self.actual=self.answer;self.assertEqual(self.r.step()['status'],'confirmed');self.assertEqual(self.posts,0)
    def test_other_answer_never_overwritten(self):
        self.actual='manual';self.assertEqual(self.r.step()['status'],'manual_present');self.assertEqual(self.posts,0)
    def test_fresh_absence_rate_wait(self):
        self.r.step();self.now+=1;self.r.step();self.assertEqual(self.posts,0);self.assertEqual(self.reads,1)
    def test_one_post_then_exact_get_confirmation(self):
        self.ready();self.assertEqual(self.r.step()['status'],'verify');self.assertEqual(self.posts,1)
        self.now+=m.BURST_GAP;self.actual=self.answer
        self.assertEqual(self.r.step()['status'],'confirmed');self.assertEqual(self.posts,1)
        self.assertEqual(self.repo.get('intents',m.INTENT)['actual_answer_sha256'],self.hash)
    def test_restart_only_reads(self):
        self.ready();self.r.step();self.now+=m.BURST_GAP
        self.r=m.Retry(SimpleNamespace(repo=self.repo,owner='owner',chat='chat'),self.wb,lambda card:True,clock=lambda:self.now)
        self.r.step();self.assertEqual(self.posts,1)
    def test_unknown_transport_never_repeats_post(self):
        self.ready();self.timeout=True;op=self.r.step();self.assertEqual(op['status'],'verify')
        self.now+=m.BURST_GAP;self.r.step();self.assertEqual(self.posts,1)
    def test_rejected_400_terminal_no_rearm(self):
        self.ready();self.response=400;self.assertEqual(self.r.step()['status'],'rejected')
        self.now+=1000;self.r.step();self.assertEqual(self.posts,1)
    def test_rejected_429_terminal_no_rearm(self):
        self.ready();self.response=429;self.assertEqual(self.r.step()['status'],'rejected')
        self.now+=1000;self.r.step();self.assertEqual(self.posts,1)
    def test_shared_pause_no_request(self):
        self.wb.pause=lambda cabinet:100;self.r.step();self.assertEqual(self.reads,0);self.assertEqual(self.posts,0)
    def test_expired_preflight_refreshed_not_sent(self):
        self.ready();self.now+=m.FRESH_SECONDS;self.r.step();self.assertEqual(self.posts,0);self.assertEqual(self.reads,2)
    def test_wrong_scope_rejected(self):
        self.i['item_id']='other';self.repo.put('intents',m.INTENT,self.i);self.conn.commit()
        with self.assertRaises(Rejected):self.r.step()
        self.assertEqual(self.reads,0);self.assertEqual(self.posts,0)
    def test_changed_text_rejected(self):
        self.i['answer']='changed';self.repo.put('intents',m.INTENT,self.i);self.conn.commit()
        with self.assertRaises(Rejected):self.r.step()
    def test_canonical_hold_blocks(self):
        self.ready();self.r.guard=lambda c:False;self.assertEqual(self.r.step()['status'],'blocked');self.assertEqual(self.posts,0)
    def test_crash_after_reserved_intent_cannot_post(self):
        op=self.r.initialize();self.r.save(op,post_consumed=True,status='write_intent')
        self.r.step();self.assertEqual(self.posts,0)
    def test_http_journal_precedes_wire_and_preserves_http400(self):
        self.r.initialize();calls=[]
        class Session:
            def request(session,method,url,*args,**kwargs):
                calls.append(self.r.operation()['http_log'][-1]['phase'])
                return SimpleNamespace(status_code=400,headers={'Authorization':'SECRET','X-Ratelimit-Retry':'600'},content=b'error',json=lambda:{'error':True,'errorText':'private detail'})
        module=SimpleNamespace(sessions=SimpleNamespace(Session=Session))
        undo=self.r.install_http_journal(module,'database.test')
        try:Session().request('GET','https://feedbacks-api.wildberries.ru/api/v1/feedback',params={'id':m.ITEM})
        finally:undo()
        self.assertEqual(calls,['before_http'])
        log=self.r.operation()['http_log'][-1];self.assertEqual(log['http_status'],400)
        self.assertNotIn('authorization',log['headers']);self.assertNotIn('errorText',str(log.get('body','')))
    def test_http_observer_blocks_other_item(self):
        self.r.initialize()
        class Session:
            def request(*a,**kw):raise AssertionError('wire must not run')
        module=SimpleNamespace(sessions=SimpleNamespace(Session=Session));undo=self.r.install_http_journal(module,'database.test')
        try:
            with self.assertRaises(Rejected):Session().request('GET','https://feedbacks-api.wildberries.ru/api/v1/feedback',params={'id':'other'})
        finally:undo()
    def test_owner_binding_required(self):
        self.i['owner_id']='other';self.repo.put('intents',m.INTENT,self.i);self.conn.commit()
        with self.assertRaises(Rejected):self.r.step()
    def test_http_post_wire_budget_persists(self):
        self.r.initialize();self.r.save(self.r.operation(),post_consumed=True,status='write_intent');self.r.allow_post=True
        calls=[]
        class Session:
            def request(session,method,url,*args,**kwargs):
                calls.append(method)
                return SimpleNamespace(status_code=204,headers={},content=b'',json=lambda:None)
        module=SimpleNamespace(sessions=SimpleNamespace(Session=Session));undo=self.r.install_http_journal(module,'database.test')
        try:
            Session().request('POST','https://feedbacks-api.wildberries.ru/api/v1/feedbacks/answer',json={'id':m.ITEM,'text':self.answer})
            self.r.allow_post=True
            with self.assertRaises(Rejected):Session().request('POST','https://feedbacks-api.wildberries.ru/api/v1/feedbacks/answer',json={'id':m.ITEM,'text':self.answer})
        finally:undo()
        self.assertEqual(calls,['POST'])
    def test_rejected_attempt_verified_empty_without_another_post(self):
        self.ready();self.response=429;self.r.step();before=self.reads
        result=self.r.verify_rejection()
        self.assertTrue(result['rejection_readback_empty']);self.assertEqual(self.posts,1)
        self.r.verify_rejection();self.assertEqual(self.reads,before+1)
    def test_rejection_readback_obeys_shared_pause(self):
        self.ready();self.response=400;self.r.step();before=self.reads
        self.wb.pause=lambda cabinet:45
        self.assertEqual(self.r.verify_rejection()['wait_seconds'],45)
        self.assertEqual(self.reads,before);self.assertEqual(self.posts,1)

if __name__=='__main__':unittest.main(verbosity=2)