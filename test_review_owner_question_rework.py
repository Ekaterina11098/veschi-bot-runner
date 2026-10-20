import unittest,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_telegram_approval import Approval,Repository,Rejected
from review_owner_question_rework import validate_target

class Tests(unittest.TestCase):
    def setUp(self):
        self.repo=Repository(sqlite3.connect(':memory:'));self.repo.setup()
        self.app=Approval(self.repo,'s','owner','chat','bot',enabled=True)
        token,_=self.app.create('token_2','questions','question','old',dict(buyer='',rating=0,text='Missing strap',pros='',cons='',article='sku'),['Old1','Old2'],123)
        card=self.repo.get('cards',token);card['status']='rework'
        self.repo.put('cards',token,card);self.repo.put('items',card['ref'],dict(status='rework',token=token,version='old'));self.repo.conn.commit()
        self.target=dict(token=token,item_id='question',expected_version='old',texts=['New1','New2'])
    def test_only_prepares_unapproved_exact_question(self):
        validate_target(self.app,self.target);self.assertEqual(self.repo.count('intents'),0)
    def test_changed_version_rejects(self):
        self.target['expected_version']='other'
        with self.assertRaises(Rejected):validate_target(self.app,self.target)
    def test_existing_intent_rejects(self):
        card=self.repo.get('cards',self.target['token']);self.repo.put('intents','i',{'ref':card['ref']});self.repo.conn.commit()
        with self.assertRaises(Rejected):validate_target(self.app,self.target)
    def test_replaced_card_rejects(self):
        card=self.repo.get('cards',self.target['token']);self.repo.put('items',card['ref'],{'token':'other','status':'rework'});self.repo.conn.commit()
        with self.assertRaises(Rejected):validate_target(self.app,self.target)

if __name__=='__main__':unittest.main()
