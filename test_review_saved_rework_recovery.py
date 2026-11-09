import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_telegram_approval import sha,Rejected
from review_saved_rework_recovery import rebind_saved_rework
class RecoveryTests(unittest.TestCase):
    def case(self):
        c=dict(status='awaiting',message_id=20,chat_id='group',version='v',texts=['draft'])
        m=dict(status='confirmed',card_token='token',old_message_id=10,message_id=20,fingerprint=sha(dict(c,message_id=10)))
        origin=dict(message_id=10,chat=dict(id='group'),from_='unused')
        origin['from']=dict(id='bot')
        e=dict(callback_query=dict(data='rv1:token:edit',message=origin,**{'from':dict(id=123,is_bot=False)}))
        r=dict(message=dict(message_id=30,text='Exact saved answer\nSignature',chat=dict(id='group'),reply_to_message=origin,**{'from':dict(id=123)}))
        return c,m,e,r
    def test_only_message_bindings_change_and_original_text_stays_exact(self):
        c,m,e,r=self.case();before=copy.deepcopy((e,r))
        a,b=rebind_saved_rework(c,'token',m,e,r,'group','bot')
        self.assertEqual((e,r),before);self.assertEqual(b['message']['text'],r['message']['text'])
        self.assertEqual(a['callback_query']['message']['message_id'],20)
        self.assertEqual(b['message']['reply_to_message']['message_id'],20)
        self.assertEqual(a['callback_query']['data'],'rv1:token:edit')
    def test_never_recovers_publication_or_changed_source(self):
        for change in ('approve','changed','unknown','actor','wrongreply'):
            c,m,e,r=self.case()
            if change=='approve':e['callback_query']['data']='rv1:token:p1'
            elif change=='changed':c['texts']=['changed']
            elif change=='unknown':m['status']='uncertain'
            elif change=='actor':r['message']['from']['id']=456
            else:r['message']['reply_to_message']['message_id']=99
            with self.assertRaises(Rejected):rebind_saved_rework(c,'token',m,e,r,'group','bot')

