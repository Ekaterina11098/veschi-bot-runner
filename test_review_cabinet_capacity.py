import json,sqlite3,unittest
from collections import Counter
from types import SimpleNamespace
from review_telegram_approval import Approval,Repository,sha
from review_approval_executor import Executor
from review_approved_worker import due_intents
class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.repo=Repository(sqlite3.connect(':memory:'));self.repo.setup();self.now=1000
        self.cfg=dict(cutover=1,owner_id='owner',chat_id='chat')
        self.app=Approval(self.repo,'secret','owner','chat','bot',enabled=True,clock=lambda:self.now)
        self.answers={};self.posts=Counter();self.fail_once=set();self.hidden=set()
    def add(self,key,cabinet='token_3',status='awaiting_preflight',retry_at=0):
        source=dict(buyer='',rating=5,text='Positive review',pros='',cons='',article='example')
        i=dict(id=key,ref=key,cabinet=cabinet,kind='feedbacks',item_id=key,version='v1',card_token=key,owner_id='owner',chat_id='chat',source_sha256=sha(source),answer='Approved answer '+key,answer_sha256=sha('Approved answer '+key),status=status,created_at=100,retry_at=retry_at)
        card=dict(ref=key,cabinet=cabinet,kind='feedbacks',item_id=key,version='v1',source=source,hashes=[i['answer_sha256']])
        self.repo.put('intents',key,i);self.repo.put('cards',key,card);self.repo.put('items',key,dict(status='approved'));self.repo.conn.commit()
    def read(self,i):return '' if i['id'] in self.hidden else self.answers.get(i['id'],'')
    def post(self,i):
        self.posts[i['id']]+=1;self.answers[i['id']]=i['answer']
        if i['id'] in self.fail_once:self.fail_once.remove(i['id']);raise TimeoutError('Unknown write outcome')
    def test_100_china_replies_while_other_cabinets_paused(self):
        self.add('paused1','token_1');self.add('paused2','token_2')
        for n in range(100):self.add('china'+str(n))
        e=Executor(self.app,lambda c:True,SimpleNamespace(pause=lambda c:720 if c!='token_3' else 0,read=self.read,post=self.post),enabled=True)
        self.fail_once={'china10'}
        for cycle in range(200):
            pending=due_intents(self.repo,self.cfg,'token_3',self.now)
            if not pending:break
            e.run(pending[0]['id'])
        self.assertEqual(len(self.posts),100);self.assertTrue(all(n==1 for n in self.posts.values()))
        self.assertEqual(sum(json.loads(r[0])['status']=='confirmed' for r in self.repo.execute('SELECT payload FROM {p}intents').fetchall()),100)
        self.assertNotIn('paused1',self.posts);self.assertNotIn('paused2',self.posts)
    def test_deferred_unknown_write_does_not_block_other_china_reviews(self):
        self.add('unknown',status='verify');self.hidden={'unknown'};self.add('next')
        e=Executor(self.app,lambda c:True,SimpleNamespace(pause=lambda c:0,read=self.read,post=self.post),enabled=True)
        e.run('unknown')
        self.assertEqual(due_intents(self.repo,self.cfg,'token_3',self.now)[0]['id'],'next')
        e.run('next');self.assertEqual(self.posts,Counter({'next':1}))
        self.assertEqual(self.repo.get('intents','unknown')['status'],'verify')
    def test_watchdog_counts_future_retries(self):
        self.add('waiting',retry_at=2000)
        self.assertEqual(due_intents(self.repo,self.cfg,'token_3',1000),[])
        self.assertEqual(len(due_intents(self.repo,self.cfg,now=float('inf'))),1)
    def test_invalid_cabinet_fails_closed(self):
        with self.assertRaises(ValueError):due_intents(self.repo,self.cfg,'wrong')
if __name__=='__main__':unittest.main()
