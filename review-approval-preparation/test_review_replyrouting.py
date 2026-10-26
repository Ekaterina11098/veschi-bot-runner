import json,sqlite3,unittest
from review_telegram_approval import Approval,Repository,Rejected
from review_telegram_receiver import Receiver
class Transport:
    def call(self,method,payload):return {'user':{'id':11},'status':'administrator'}
class Routing(unittest.TestCase):
    def fixture(self,cab='token_1',kind='feedbacks',change=False,status='rework'):
        repo=Repository(sqlite3.connect(':memory:'));repo.setup()
        a=Approval(repo,'s',11,22,33,enabled=True)
        source=dict(buyer='',rating=4,text='source',pros='',cons='',article='example')
        old,_=a.create(cab,kind,'example','v1',source,['old'],101)
        current,_=a.create(cab,kind,'example','v2',dict(source,text='changed') if change else source,['current'],102)
        with repo.transaction():
            card=repo.get('cards',current);card['status']=status;repo.put('cards',current,card)
            item=repo.get('items',card['ref']);item['status']=status;repo.put('items',card['ref'],item)
        update={'message':{'message_id':103,'from':{'id':11},'chat':{'id':22,'type':'private'},'text':'owner revised text','reply_to_message':{'message_id':101,'from':{'id':33}}}}
        seen=[]
        rec=Receiver(a,Transport(),lambda c: seen.append(c['version']) or True)
        return repo,rec,update,current,seen
    def test_all_cabinets_and_kinds(self):
        for cab in ('token_1','token_2','token_3'):
            for kind in ('feedbacks','questions'):
                with self.subTest(cab=cab,kind=kind):
                    repo,r,u,current,seen=self.fixture(cab,kind)
                    result=r.receive(u,'s');again=r.receive(u,'s')
                    self.assertEqual(result['status'],'revision_requested')
                    self.assertTrue(again['duplicate']);self.assertEqual(repo.count('intents'),0)
                    self.assertEqual(repo.get('events',result['revision_event_id'])['token'],current)
                    self.assertEqual(seen,['v2','v2'])
    def test_changed_source_rejected(self):
        repo,r,u,_,_=self.fixture(change=True)
        with self.assertRaises(Rejected):r.receive(u,'s')
        self.assertEqual(repo.count('intents'),0)
    def test_finished_or_held_rejected(self):
        for status in ('approved','sent','held','uncertain','open'):
            repo,r,u,_,_=self.fixture(status=status)
            with self.assertRaises(Rejected):r.receive(u,'s')
    def test_current_guard_still_required(self):
        repo,r,u,_,_=self.fixture();r.reconcile=lambda c:False
        with self.assertRaises(Rejected):r.receive(u,'s')
    def test_wrong_owner_rejected(self):
        repo,r,u,_,_=self.fixture();u['message']['from']['id']=12
        with self.assertRaises(Rejected):r.receive(u,'s')
if __name__=='__main__':unittest.main()
