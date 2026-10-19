import unittest,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_telegram_approval import Approval,Repository,Rejected
from confirm_selected_chat import confirm
class Tests(unittest.TestCase):
    def setUp(self):
        self.repo=Repository(sqlite3.connect(':memory:'));self.repo.setup();self.app=Approval(self.repo,'s','owner','chat','bot',enabled=True)
        self.token,_=self.app.create('token_2','feedbacks','id','v',dict(buyer='A',rating=5,text='',pros='',cons='',article='sku'),['first','second'],123)
        with self.repo.transaction():
            c=self.repo.get('cards',self.token);c.update(status='selected',selected=1,nonce='n');self.repo.put('cards',self.token,c)
        self.expected=dict(version='v',answer_sha256=c['hashes'][1])
    def test_exact_selected_variant_once(self):
        r=confirm(self.app,lambda c:True,self.token,lambda:None,self.expected)
        i=self.repo.get('intents',r['intent_id']);self.assertEqual(i['answer'],'second');self.assertNotIn('callback_id',i)
        confirm(self.app,lambda c:True,self.token,lambda:None,self.expected);self.assertEqual(self.repo.count('intents'),1)
    def test_changed_selection_blocked(self):
        self.expected['answer_sha256']='wrong'
        with self.assertRaises(Rejected):confirm(self.app,lambda c:True,self.token,lambda:None,self.expected)
        self.assertEqual(self.repo.count('intents'),0)
    def test_guard_blocks(self):
        with self.assertRaises(Rejected):confirm(self.app,lambda c:False,self.token,lambda:None,self.expected)
        self.assertEqual(self.repo.count('intents'),0)
    def test_unsigned_complete_question_reply(self):
        from review_approval_revision import ready_owner_text
        self.assertTrue(ready_owner_text('Здравствуйте! 😊 Все замеры манишки, в том числе для 54-го размера, указаны в карточке товара в описании товара.'))
        self.assertFalse(ready_owner_text('Здравствуйте! Исправь пожалуйста ответ на вопрос, добавь размеры и напиши покупателю более подробно.'))
