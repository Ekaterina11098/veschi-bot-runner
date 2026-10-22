import sqlite3,sys,unittest,copy
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_telegram_approval import Approval,Repository,identity,sha
from review_approval_cleanup import cleanup_completed
from review_approval_card_delivery import notify_owner_receipt
class CleanupTests(unittest.TestCase):
    def setup_case(self,state='confirmed',owner='owner',cabinet='token_1',kind='feedbacks'):
        repo=Repository(sqlite3.connect(':memory:'));repo.setup()
        a=Approval(repo,'s','owner','chat','bot',clock=lambda:1000)
        ref=identity(cabinet,kind,'id')
        card=dict(ref=ref,cabinet=cabinet,kind=kind,item_id='id',version='v',hashes=[sha('answer')],message_id=10,source={'article':'sku'})
        i=dict(card, id='i',card_token='c',answer='answer',answer_sha256=sha('answer'),actual_answer_sha256=sha('answer'),owner_id=owner,chat_id='chat',status=state)
        repo.put('cards','c',card);repo.put('items',ref,{'token':'c','status':'sent' if state=='confirmed' else 'approved'})
        repo.put('intents','i',i)
        repo.put('cards','unprocessed',dict(card,ref=identity(cabinet,kind,'other'),message_id=99))
        for n,stage in enumerate(('approved','verifying','accepted','public'),20):
            repo.put('events','owner-receipt:i:'+stage,dict(intent_id='i',stage=stage,status='confirmed',message_id=n))
        repo.conn.commit()
        tg=Mock();tg.call.return_value=True
        return a,tg,i
    def test_completed_all_cabinets_and_types_delete_only_tracked_bot_messages(self):
        for c in ('token_1','token_2','token_3'):
            for k in ('feedbacks','questions'):
                a,tg,i=self.setup_case(cabinet=c,kind=k)
                before=copy.deepcopy(a.repo.get('intents','i'))
                result=cleanup_completed(a,tg)
                self.assertEqual(result['deleted'],5)
                self.assertEqual({call.args[1]['message_id'] for call in tg.call.call_args_list},{10,20,21,22,23})
                self.assertTrue(all(call.args[0]=='deleteMessage' for call in tg.call.call_args_list))
                self.assertEqual(a.repo.get('intents','i'),before)
                self.assertEqual(a.repo.get('cards','unprocessed')['message_id'],99)
                cleanup_completed(a,tg);self.assertEqual(tg.call.call_count,5)
    def test_approved_card_removed_while_wb_pending_but_error_remains(self):
        a,tg,i=self.setup_case(state='verify')
        a.repo.put('events','owner-problem:i',dict(intent_id='i',message_id=50,status='confirmed'));a.repo.conn.commit()
        cleanup_completed(a,tg)
        self.assertEqual({call.args[1]['message_id'] for call in tg.call.call_args_list},{10,20,21,22,23})
    def test_old_revision_chain_removed_after_final_approval(self):
        a,tg,i=self.setup_case(state='awaiting_preflight')
        card=copy.deepcopy(a.repo.get('cards','c'));card['message_id']=11
        a.repo.put('cards','old',card)
        a.repo.put('events','edit:old',{'token':'old'})
        a.repo.put('events','revision-delivery:old',{'revision_event_id':'edit:old','message_id':12})
        a.repo.conn.commit()
        cleanup_completed(a,tg)
        self.assertEqual({c.args[1]['message_id'] for c in tg.call.call_args_list},{10,11,12,20,21,22,23})
        self.assertEqual(a.repo.get('intents','i')['status'],'awaiting_preflight')
    def test_new_actionable_revision_is_preserved(self):
        a,tg,i=self.setup_case()
        a.repo.put('items',i['ref'],{'token':'unprocessed','status':'rework'});a.repo.conn.commit()
        cleanup_completed(a,tg)
        self.assertNotIn(99,{c.args[1]['message_id'] for c in tg.call.call_args_list})
    def test_only_exact_completed_owner_reply_is_removed(self):
        a,tg,i=self.setup_case(state='awaiting_preflight')
        def incoming(mid,text='answer',owner='owner',reply=10):
            return {'update':{'message':{'message_id':mid,'text':text,'from':{'id':owner},'chat':{'id':'chat','type':'private'},'reply_to_message':{'message_id':reply,'from':{'id':'bot'}}}}}
        for key,value in [('exact',incoming(70)),('othertext',incoming(71,'other draft')),('foreign',incoming(72,owner='other')),('unrelated',incoming(73,reply=99))]:
            a.repo.put('events','telegram-ingress:'+key,value)
        a.repo.conn.commit()
        cleanup_completed(a,tg)
        deleted={c.args[1]['message_id'] for c in tg.call.call_args_list}
        self.assertIn(70,deleted)
        self.assertTrue(deleted.isdisjoint({71,72,73,99}))
    def test_group_owner_reply_swept_from_legacy_worker_chat(self):
        a,tg,i=self.setup_case()
        a.group=dict(enabled=True,destination_verified=True,chat_id='group')
        c=a.repo.get('cards','c');c['chat_id']='group'
        i['chat_id']='group'
        a.repo.put('cards','c',c);a.repo.put('intents','i',i)
        for mid,text,owner,chat,reply in ((70,'answer','owner','group',10),(71,'other draft','owner','group',10),(72,'answer','other','group',10),(73,'answer','owner','foreign',10),(74,'answer','owner','group',99)):
            a.repo.put('events','telegram-ingress:'+str(mid),{'update':{'message':{
                'message_id':mid,'text':text,'from':{'id':owner},
                'chat':{'id':chat,'type':'supergroup'},
                'reply_to_message':{'message_id':reply,'from':{'id':'bot'}}}}})
        a.repo.conn.commit()
        before=copy.deepcopy(a.repo.get('intents','i'))
        cleanup_completed(a,tg)
        self.assertEqual(a.chat,'chat')
        group_deleted={x.args[1]['message_id'] for x in tg.call.call_args_list if x.args[1]['chat_id']=='group'}
        self.assertEqual(group_deleted,{10,70})
        self.assertEqual(a.repo.get('intents','i'),before)
        count=tg.call.call_count;cleanup_completed(a,tg)
        self.assertEqual(tg.call.call_count,count)
    def test_unverified_group_not_swept(self):
        a,tg,i=self.setup_case()
        a.group=dict(enabled=True,destination_verified=False,chat_id='group')
        c=a.repo.get('cards','c');c['chat_id']='group';i['chat_id']='group'
        a.repo.put('cards','c',c);a.repo.put('intents','i',i);a.repo.conn.commit()
        cleanup_completed(a,tg);tg.call.assert_not_called()
    def test_foreign_owner_and_bad_checksum_never_delete(self):
        a,tg,i=self.setup_case(owner='other');cleanup_completed(a,tg);tg.call.assert_not_called()
        a,tg,i=self.setup_case();i['answer_sha256']='wrong';a.repo.put('intents','i',i);a.repo.conn.commit()
        cleanup_completed(a,tg);tg.call.assert_not_called()
    def test_normal_receipts_suppressed_errors_still_delivered(self):
        for state in ('awaiting_preflight','verify','confirmed'):
            a,tg,i=self.setup_case(state=state)
            self.assertEqual(notify_owner_receipt(a,tg,i)['status'],'suppressed')
            self.assertTrue(all(call.args[0]=='deleteMessage' for call in tg.call.call_args_list))
        a,tg,i=self.setup_case(state='blocked');tg.call.return_value={'chat':{'id':'chat'},'message_id':60}
        self.assertEqual(notify_owner_receipt(a,tg,i)['status'],'confirmed')
        self.assertEqual(tg.call.call_args.args[0],'notifyOwnerReviewReceipt')
    def test_deletion_failure_does_not_change_wb_state_or_loop(self):
        a,tg,i=self.setup_case();tg.call.side_effect=TimeoutError()
        self.assertEqual(cleanup_completed(a,tg)['unconfirmed'],5)
        cleanup_completed(a,tg);self.assertEqual(tg.call.call_count,5)
        self.assertEqual(a.repo.get('intents','i')['status'],'confirmed')
if __name__=='__main__':unittest.main()
