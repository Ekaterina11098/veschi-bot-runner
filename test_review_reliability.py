"""Crash/replay tests at authenticated receipt and unknown WB write boundaries."""
import sys,sqlite3,json,base64,unittest,io,urllib.error
from pathlib import Path
from unittest.mock import Mock,patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_telegram_approval import Approval,Repository,sha,Rejected
from review_approval_inbox import drain,process_update,PREFIX
from review_approval_executor import Executor,ExplicitRateLimit

class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.repo=Repository(sqlite3.connect(':memory:'));self.repo.setup();self.now=1000
        self.a=Approval(self.repo,'secret','owner','chat','bot',enabled=True,clock=lambda:self.now)
        self.source=dict(buyer='Имя',rating=5,text='Отзыв',pros='',cons='',article='sku')
        self.tg=Mock();self.tg.call.return_value=True
        self.bridge=SimpleNamespace(project=lambda card:dict(complete=True,ref=card['ref'],hold=False,answered=False,publication_state='idle',version=card['version'],hashes=card['hashes'],source_sha256=sha(card['source'])))
    def card(self,c='token_1',k='feedbacks',texts=None):
        return self.a.create(c,k,c+k,'v1',self.source,texts or ['Первый','Второй'],10)[0]
    def update(self,token,action,event=1):
        return dict(update_id=event,callback_query=dict(id='event'+str(event),data='rv1:'+token+':'+action,**{'from':{'id':'owner'}},message={'message_id':10,'chat':{'id':'chat','type':'private'},'from':{'id':'bot'}}))
    def test_explicit_publish_buttons_all_cabinets_and_both_kinds(self):
        for c in ('token_1','token_2','token_3'):
            for k in ('feedbacks','questions'):
                token=self.card(c,k)
                buttons=self.a.view(token)['reply_markup']['inline_keyboard']
                self.assertEqual(buttons[0][0]['text'],'Опубликовать вариант 1')
                result=self.a.handle(self.update(token,'p2',len(self.repo.execute('SELECT id FROM events').fetchall())+1),'secret')
                i=self.repo.get('intents',result['result']['intent_id']);self.assertEqual(i['answer'],'Второй')
                duplicate=self.a.handle(self.update(token,'p2',100+len(self.repo.execute('SELECT id FROM events').fetchall())),'secret')
                self.assertTrue(duplicate['duplicate'])
                with self.assertRaises(Rejected):self.a.handle(self.update(token,'p1',500),'secret')
        self.assertEqual(self.repo.count('intents'),6)
    def test_one_revised_text_has_explicit_confirmation_and_rework(self):
        token=self.card(texts=['Правка'])
        keyboard=self.a.view(token)['reply_markup']['inline_keyboard']
        self.assertEqual(keyboard[0][0]['text'],'Подтвердить публикацию')
        self.assertIn('edit',[b['callback_data'].split(':')[-1] for row in keyboard for b in row])
        with self.assertRaises(Rejected):self.a.handle(self.update(token,'p2'),'secret')
        self.assertEqual(self.repo.count('intents'),0)
    def test_legacy_choice_still_requires_confirmation(self):
        token=self.card();self.a.handle(self.update(token,'v1'),'secret')
        self.assertEqual(self.repo.count('intents'),0)
    def test_approval_receipt_never_waits_on_wb_and_replays_once(self):
        token=self.card();update=self.update(token,'p1')
        with patch('review_approval_process.Executor',side_effect=AssertionError('WB must be asynchronous')):
            result=process_update(self.a,self.bridge,self.tg,update)
            again=process_update(self.a,self.bridge,self.tg,update)
        self.assertEqual(result['result']['decision'],'approved');self.assertTrue(again['already_processed'])
        self.assertEqual(self.repo.count('intents'),1)
    def test_crash_after_durable_decision_replays_without_second_intent(self):
        token=self.card();update=self.update(token,'p1');self.a.handle(update,'secret')
        result=process_update(self.a,self.bridge,self.tg,update)
        self.assertEqual(result['result']['decision'],'approved');self.assertEqual(self.repo.count('intents'),1)
    def test_inbox_fallback_after_dispatch_failure_and_no_replay(self):
        token=self.card();update=self.update(token,'p1')
        rows=[(PREFIX+'test',{'sealed_update':'sealed','update_id':1})]
        with patch('review_approval_inbox.pending',return_value=rows),patch('review_approval_process.decrypt_update',return_value=update):
            self.assertEqual(drain(self.a,self.bridge,self.tg,'key')['processed'],1)
            self.assertEqual(drain(self.a,self.bridge,self.tg,'key')['processed'],1)
        self.assertEqual(self.repo.count('intents'),1)
    def test_inbox_decrypt_failure_rejects_without_publication(self):
        with patch('review_approval_inbox.pending',return_value=[(PREFIX+'test',{'sealed_update':'corrupt'})]),patch('review_approval_process.decrypt_update',side_effect=ValueError('tampered')):
            self.assertEqual(drain(self.a,self.bridge,self.tg,'key')['rejected'],1)
        self.assertEqual(self.repo.count('intents'),0)
    def test_inbox_temporary_failure_preserves_order_and_retries(self):
        token=self.card();update=self.update(token,'p1')
        rows=[(PREFIX+'one',{'sealed_update':'one','update_id':1}),(PREFIX+'two',{'sealed_update':'two','update_id':2})]
        with patch('review_approval_inbox.pending',return_value=rows),patch('review_approval_process.decrypt_update',side_effect=lambda raw,key:self.update(token,'p1',1 if raw=='one' else 2)),patch('review_approval_inbox.process_update',side_effect=TimeoutError()):
            self.assertEqual(drain(self.a,self.bridge,self.tg,'key')['retry'],1)
            self.assertIsNone(self.repo.get('events','telegram-inbox:'+PREFIX+'two'))
            self.assertEqual(drain(self.a,self.bridge,self.tg,'key')['retry'],0)
        self.now+=11
        with patch('review_approval_inbox.pending',return_value=rows[:1]),patch('review_approval_process.decrypt_update',return_value=update):
            self.assertEqual(drain(self.a,self.bridge,self.tg,'key')['processed'],1)
        self.assertEqual(self.repo.count('intents'),1)
    def test_inbox_never_accepts_internal_publication_commands(self):
        rows=[(PREFIX+'test',{'sealed_update':'sealed','update_id':1})]
        with patch('review_approval_inbox.pending',return_value=rows),patch('review_approval_process.decrypt_update',return_value={'update_id':1,'resume_intent':'i'}):
            self.assertEqual(drain(self.a,self.bridge,self.tg,'key')['rejected'],1)
        self.assertEqual(self.repo.count('intents'),0)
    def test_one_card_outage_does_not_block_other_cabinet(self):
        first=self.card('token_1');second=self.card('token_3')
        card=self.repo.get('cards',second);card['message_id']=11
        self.repo.put('cards',second,card);self.repo.conn.commit()
        one=self.update(first,'p1',1);two=self.update(second,'p1',2);two['callback_query']['message']['message_id']=11
        rows=[(PREFIX+'one',{'sealed_update':'one','update_id':1}),(PREFIX+'two',{'sealed_update':'two','update_id':2})]
        native=process_update
        def receive(*args,**kwargs):
            if args[3]['update_id']==1:raise TimeoutError()
            return native(*args,**kwargs)
        with patch('review_approval_inbox.pending',return_value=rows),patch('review_approval_process.decrypt_update',side_effect=lambda raw,key:one if raw=='one' else two),patch('review_approval_inbox.process_update',side_effect=receive):
            result=drain(self.a,self.bridge,self.tg,'key')
        self.assertEqual(result,{'processed':1,'rejected':0,'retry':1});self.assertEqual(self.repo.count('intents'),1)
    def test_readback_429_and_timeout_keep_verify_without_second_post(self):
        token=self.card();result=self.a.handle(self.update(token,'p1'),'secret');iid=result['result']['intent_id']
        posts=[]
        wb=SimpleNamespace(pause=lambda c:0,read=Mock(side_effect=['',ExplicitRateLimit(120)]),post=lambda i:posts.append(i['id']))
        executor=Executor(self.a,lambda c:True,wb,enabled=True)
        state=executor.run(iid);self.assertEqual(state['status'],'verify');self.assertEqual(state['retry_at'],1120)
        executor.run(iid);self.assertEqual(len(posts),1);self.assertEqual(wb.read.call_count,2)
        self.now=1121;wb.read=Mock(side_effect=TimeoutError())
        state=executor.run(iid);self.assertEqual(state['status'],'verify');self.assertEqual(state['retry_at'],1181)
        self.assertEqual(len(posts),1)
    def test_failed_card_deletion_retries_bound_message_only_after_pause(self):
        from review_approval_card_delivery import dismiss_approved
        token=self.card();self.a.handle(self.update(token,'p1'),'secret')
        self.tg.call.side_effect=TimeoutError()
        self.assertEqual(dismiss_approved(self.a,self.tg,token)['status'],'uncertain')
        self.now+=31;self.tg.call.side_effect=None;self.tg.call.return_value=True
        self.assertEqual(dismiss_approved(self.a,self.tg,token)['status'],'confirmed')
        self.assertEqual(self.repo.count('intents'),1)
        self.assertEqual(self.tg.call.call_args.args,('deleteMessage',{'chat_id':'chat','message_id':10}))
    def test_lost_ui_ack_can_be_reconciled_idempotently(self):
        from review_telegram_runtime import TelegramTransport
        for method,description,payload in [('editMessageText','Bad Request: message is not modified',{'text':'same'}),('deleteMessage','Bad Request: message to delete not found',{})]:
            transport=TelegramTransport('test',opener=Mock(side_effect=urllib.error.HTTPError('https://unit.invalid',400,'Bad',None,io.BytesIO(json.dumps({'description':description}).encode()))))
            self.assertIs(transport.call(method,payload),True)
    def test_uncertain_ui_keeps_approval_and_requests_only_ui_repair(self):
        token=self.card();update=self.update(token,'p1');self.tg.call.side_effect=TimeoutError()
        with self.assertRaisesRegex(RuntimeError,'UI repair'):process_update(self.a,self.bridge,self.tg,update)
        self.assertEqual(self.repo.count('intents'),1)
        self.now+=31;self.tg.call.side_effect=None;self.tg.call.return_value=True
        result=process_update(self.a,self.bridge,self.tg,update)
        self.assertEqual(result['result']['decision'],'approved');self.assertEqual(self.repo.count('intents'),1)

if __name__=='__main__':unittest.main()
