import unittest,sys,sqlite3
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_telegram_approval import Approval,Repository,Rejected
from review_owner_rework_batch import validate_target
class Tests(unittest.TestCase):
    def setUp(self):
        self.repo=Repository(sqlite3.connect(':memory:'));self.repo.setup();self.app=Approval(self.repo,'s','owner','chat','bot',enabled=True)
        self.token,_=self.app.create('token_1','feedbacks','id','old',dict(buyer='A',rating=4,text='Review',pros='',cons='',article='sku'),['old1','old2'],123)
        self.target=dict(token=self.token,cabinet='token_1',item_id='id',texts=['New one','New two'])
    def test_preparation_creates_no_approval(self):
        validate_target(self.app,self.target);self.assertEqual(self.repo.count('intents'),0)
    def test_approved_or_replaced_card_blocks(self):
        c=self.repo.get('cards',self.token)
        self.repo.put('items',c['ref'],dict(token='other',status='open'));self.repo.conn.commit()
        with self.assertRaises(Rejected):validate_target(self.app,self.target)
    def test_wrong_identity_blocks(self):
        self.target['cabinet']='token_2'
        with self.assertRaises(Rejected):validate_target(self.app,self.target)
    def test_identical_variants_block(self):
        self.target['texts']=['same','same']
        with self.assertRaises(Rejected):validate_target(self.app,self.target)
