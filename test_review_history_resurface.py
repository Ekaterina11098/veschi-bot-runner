import copy,json,sys,unittest,sqlite3
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_telegram_approval import Approval,Repository,identity,sha
from review_history_resurface import resurface

class ResurfaceTests(unittest.TestCase):
    def case(self,status='awaiting',item_status='open'):
        r=Repository(sqlite3.connect(':memory:'));r.setup()
        a=Approval(r,'secret','owner','private','bot',enabled=True,clock=lambda:1000)
        a.group=dict(enabled=True,destination_verified=True,chat_id='group')
        c=dict(ref=identity('token_3','feedbacks','id'),cabinet='token_3',kind='feedbacks',
               item_id='id',version='v',hashes=[sha('answer')],texts=['answer'],
               message_id=10,chat_id='group',status=status,source=dict(article='sku',buyer='Buyer',
               rating=4,text='Complaint',pros='',cons=''),selected=None,nonce=None)
        r.put('cards','card',c);r.put('items',c['ref'],dict(token='card',status=item_status));r.conn.commit()
        t=Mock();t.call.return_value=dict(message_id=20,chat=dict(id='group'))
        return a,t,c
    def test_exact_binding_only_and_repeat_does_not_send(self):
        a,t,c=self.case();before=copy.deepcopy(c);item=a.repo.get('items',c['ref'])
        result=resurface(a,t,'card','batch');self.assertEqual(result['status'],'confirmed')
        after=a.repo.get('cards','card');self.assertEqual(after.pop('message_id'),20)
        before.pop('message_id');self.assertEqual(after,before)
        self.assertEqual(a.repo.get('items',c['ref']),item)
        self.assertEqual(a.repo.execute('SELECT count(*) FROM {p}intents').fetchone()[0],0)
        self.assertEqual(t.call.call_args.args[1]['text'],a.view('card')['text'])
        resurface(a,t,'card','batch');self.assertEqual(t.call.call_count,1)
    def test_unknown_send_is_never_repeated_or_bound(self):
        a,t,c=self.case();t.call.side_effect=TimeoutError()
        self.assertEqual(resurface(a,t,'card','batch')['status'],'uncertain')
        resurface(a,t,'card','batch');self.assertEqual(t.call.call_count,1)
        self.assertEqual(a.repo.get('cards','card')['message_id'],10)
    def test_preserved_hold_sent_and_approved_intent(self):
        for status,itemstatus in [('held','held'),('sent','sent'),('approved','approved')]:
            a,t,c=self.case(status,itemstatus)
            self.assertEqual(resurface(a,t,'card','batch')['status'],'skipped');t.call.assert_not_called()
        a,t,c=self.case();a.repo.put('intents','i',dict(ref=c['ref'],status='awaiting_preflight'));a.repo.conn.commit()
        resurface(a,t,'card','batch');t.call.assert_not_called()
    def test_pending_rework_preserved_and_wrong_chat_rejected(self):
        a,t,c=self.case('rework','rework');resurface(a,t,'card','batch')
        self.assertEqual(a.repo.get('cards','card')['status'],'rework')
        a,t,c=self.case();c['chat_id']='foreign';a.repo.put('cards','card',c);a.repo.conn.commit()
        resurface(a,t,'card','batch');t.call.assert_not_called()
    def test_decision_change_after_claim_blocks_send(self):
        a,t,c=self.case();original=a.repo.get;calls=0
        def get(table,key,**kw):
            nonlocal calls
            v=original(table,key,**kw)
            if table=='items':
                calls+=1
                if calls==2:v['status']='approved'
            return v
        a.repo.get=get
        self.assertEqual(resurface(a,t,'card','batch')['status'],'skipped_changed')
        t.call.assert_not_called()

