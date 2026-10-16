import unittest,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_telegram_approval import Approval,Repository,Rejected
class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.repo=Repository(sqlite3.connect(':memory:'));self.repo.setup()
        self.app=Approval(self.repo,'secret',11,22,33,enabled=True)
        self.context=dict(buyer='Татьяна',rating=4,text='Отзыв',pros='',cons='',article='664-MiraBag-blue')
        self.token,_=self.app.create('token_1','feedbacks','x','edited-v2',self.context,['Точный текст владельца'],123)
    def click(self,action,event):
        return self.app.handle({'callback_query':{'id':event,'data':'rv1:'+self.token+':'+action,'from':{'id':11},'message':{'message_id':123,'chat':{'id':22,'type':'private'},'from':{'id':33}}}},'secret')
    def test_exact_text_needs_new_confirmation(self):
        self.click('v1','select');self.assertEqual(self.repo.count('intents'),0)
        nonce=self.repo.get('cards',self.token)['nonce']
        r=self.click('ok.'+nonce,'confirm')
        self.assertEqual(self.repo.get('intents',r['result']['intent_id'])['answer'],'Точный текст владельца')
    def test_second_variant_rejected(self):
        with self.assertRaises(Rejected):self.click('v2','bad')
    def test_reply_saved_and_resumable_once(self):
        self.click('edit','edit');r=self.app.record_edit(self.token,11,22,123,'Новый текст')
        self.assertEqual(self.repo.get('events',r['revision_event_id'])['instruction'],'Новый текст')
        self.assertTrue(self.app.record_edit(self.token,11,22,123,'Новый текст')['duplicate'])
if __name__=='__main__':unittest.main()

