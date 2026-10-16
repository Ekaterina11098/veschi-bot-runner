import unittest,sys,sqlite3
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_telegram_approval import Approval,Repository,Rejected
from confirm_owner_selected import confirm
class Tests(unittest.TestCase):
    def setUp(self):
        self.repo=Repository(sqlite3.connect(':memory:'));self.repo.setup();self.app=Approval(self.repo,'s','owner','chat','bot',enabled=True)
        source=dict(buyer='A',rating=5,text='t',pros='',cons='',article='sku')
        self.token,_=self.app.create('token_1','feedbacks','id','v2',source,['Owner exact answer'],123)
        with self.repo.transaction():
            c=self.repo.get('cards',self.token);c.update(status='selected',selected=0,nonce='n');self.repo.put('cards',self.token,c)
    def test_owner_channel_audited_exact_text_once(self):
        results=[];r=confirm(self.app,lambda c:True,self.token,lambda:results.append(self.repo.count('intents')))
        self.assertEqual(results,[0,1]);i=self.repo.get('intents',r['intent_id'])
        self.assertEqual(i['answer'],'Owner exact answer');self.assertEqual(i['authorization_channel'],'owner_chat');self.assertNotIn('callback_id',i)
        confirm(self.app,lambda c:True,self.token,lambda:None);self.assertEqual(self.repo.count('intents'),1)
    def test_hold_or_unselected_does_not_approve(self):
        with self.assertRaises(Rejected):confirm(self.app,lambda c:False,self.token,lambda:None)
        self.assertEqual(self.repo.count('intents'),0)
    def test_changed_source_blocks_after_authorization_backup(self):
        def change():
            with self.repo.transaction():
                c=self.repo.get('cards',self.token);c['version']='changed';self.repo.put('cards',self.token,c)
        with self.assertRaises(Rejected):confirm(self.app,lambda c:True,self.token,change)
        self.assertEqual(self.repo.count('intents'),0)
if __name__=='__main__':unittest.main()

