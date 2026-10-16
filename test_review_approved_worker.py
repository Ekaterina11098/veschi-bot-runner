import unittest,sqlite3,sys,json
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_telegram_approval import Approval,Repository,sha
from review_approval_executor import Executor,ExplicitRateLimit
from review_approved_worker import due_intents
class Tests(unittest.TestCase):
    def setUp(self):
        self.conn=sqlite3.connect(':memory:');self.repo=Repository(self.conn);self.repo.setup();self.now=1000
        self.a=Approval(self.repo,'s','owner','chat','bot',enabled=True,clock=lambda:self.now)
        self.source=dict(buyer='A',rating=5,text='ok',pros='',cons='',article='sku')
        self.i={'id':'i','ref':'ref','cabinet':'token_2','kind':'feedbacks','item_id':'review','version':'v1','card_token':'card','owner_id':'owner','chat_id':'chat','source_sha256':sha(self.source),'answer':'approved','answer_sha256':sha('approved'),'status':'awaiting_preflight','created_at':100}
        self.card={k:self.i[k] for k in ('ref','cabinet','kind','item_id','version')};self.card.update(source=self.source,hashes=[sha('approved')])
        self.repo.put('intents','i',self.i);self.repo.put('cards','card',self.card);self.repo.put('items','ref',{'status':'approved'});self.conn.commit()
        self.actual='';self.posts=[];self.reads=[];self.pause=0;self.fail=False;self.saved=[]
        self.wb=SimpleNamespace(pause=lambda c:self.pause,read=self.read,post=self.post)
        self.e=Executor(self.a,lambda c:True,self.wb,enabled=True,preserve=lambda:self.saved.append(self.repo.get('intents','i')['status']))
    def read(self,i):self.reads.append(i['cabinet']);return self.actual
    def post(self,i):
        self.assertEqual(self.repo.get('intents','i')['status'],'verify');self.assertIn('verify',self.saved)
        self.posts.append((i['cabinet'],i['answer']))
        if self.fail:raise TimeoutError()
        self.actual=i['answer']
    def test_publish_exact_text_and_readback_all_cabinets(self):
        for cabinet in ('token_1','token_2','token_3'):
            self.i.update(cabinet=cabinet,status='awaiting_preflight');self.card['cabinet']=cabinet
            self.repo.put('intents','i',self.i);self.repo.put('cards','card',self.card);self.conn.commit();self.actual=''
            self.assertEqual(self.e.run('i')['status'],'confirmed');self.assertEqual(self.posts[-1],(cabinet,'approved'))
    def test_existing_matching_or_other_answer_never_posts(self):
        for actual,status in [('approved','confirmed'),('manual','manual_present')]:
            self.i['status']='awaiting_preflight';self.repo.put('intents','i',self.i);self.conn.commit();self.actual=actual
            self.assertEqual(self.e.run('i')['status'],status)
        self.assertEqual(self.posts,[])
    def test_unknown_write_then_restart_only_reads(self):
        self.fail=True;self.assertEqual(self.e.run('i')['status'],'verify')
        self.e.run('i');self.assertEqual(len(self.posts),1)
    def test_read_cooldown_does_not_starve_write_after_13_minutes(self):
        def read(i):self.pause=780;return ''
        self.wb.read=read
        self.e.run('i');self.assertFalse(self.posts)
        self.now+=781;self.pause=0;self.wb.read=self.read
        self.assertEqual(self.e.run('i')['status'],'confirmed');self.assertEqual(len(self.posts),1)
    def test_expired_preflight_or_question_requires_new_read(self):
        self.i.update(preflight_verified_at=1);self.repo.put('intents','i',self.i);self.conn.commit()
        self.e.run('i');self.assertEqual(len(self.reads),2)
    def test_hold_and_changed_text_block_writes(self):
        self.e.guard=lambda c:False
        self.assertEqual(self.e.run('i')['status'],'blocked');self.assertFalse(self.posts)
    def test_selector_only_bound_new_approvals_and_prioritizes_verification(self):
        cfg={'cutover':50,'owner_id':'owner','chat_id':'chat'}
        self.assertEqual(len(due_intents(self.repo,cfg)),1)
        for field,value in [('owner_id','other'),('chat_id','other'),('created_at',1),('status','confirmed')]:
            item=dict(self.i,**{field:value});self.repo.put('intents','i',item);self.conn.commit()
            self.assertEqual(due_intents(self.repo,cfg),[])
        self.repo.put('intents','i',self.i)
        other=dict(self.i,id='verify',status='verify',created_at=200);self.repo.put('intents','verify',other);self.conn.commit()
        self.assertEqual(due_intents(self.repo,cfg)[0]['id'],'verify')
if __name__=='__main__':unittest.main()

