import copy
import io
import json
import sqlite3
import unittest
import tempfile
import os
import concurrent.futures
from review_telegram_approval import Approval, Repository, Rejected, identity
from review_telegram_receiver import Receiver
from review_telegram_runtime import CanonicalGuard, TelegramTransport

class Telegram:
    def __init__(self): self.calls=[]; self.fail=False
    def call(self, method, payload):
        self.calls.append((method,payload))
        if self.fail: raise TimeoutError()
        return {'ok':True}

class Tests(unittest.TestCase):
    def setUp(self):
        self.conn=sqlite3.connect(':memory:'); self.repo=Repository(self.conn); self.repo.setup()
        self.now=1000
        self.a=Approval(self.repo,'secret',11,22,33,enabled=True,clock=lambda:self.now)
        self.source=dict(buyer='Елена',rating=4,text='Выбрала другую модель',pros='',cons='',article='548-GloriaBag-brown')
        self.token,self.view=self.a.create('token_1','feedbacks','review','v1',self.source,['Ответ один','Ответ два'],101)
        self.tg=Telegram(); self.receiver=Receiver(self.a,self.tg,lambda card:True)
    def update(self,action,event='event'):
        return {'callback_query':{'id':event,'from':{'id':11},'data':'rv1:'+self.token+':'+action,
            'message':{'message_id':101,'chat':{'id':22,'type':'private'},'from':{'id':33}}}}
    def handle(self,action,event='event'):return self.a.handle(self.update(action,event),'secret')
    def selected(self):
        self.handle('v2','select')
        return self.repo.get('cards',self.token)['nonce']
    def test_choice_does_not_publish(self):
        self.selected();self.assertEqual(self.repo.count('intents'),0)
    def test_exact_confirmation(self):
        nonce=self.selected();result=self.handle('ok.'+nonce,'confirm')
        intent=self.repo.get('intents',result['result']['intent_id'])
        self.assertEqual(intent['answer'],'Ответ два');self.assertEqual(intent['status'],'awaiting_preflight')
    def test_approved_ui_explains_disabled_and_pause(self):
        nonce=self.selected();self.handle('ok.'+nonce,'confirm')
        card=self.repo.get('cards',self.token)
        card.update(publication_enabled=False,retry_at=self.now+62)
        text=self.a.view(self.token,card)['text']
        self.assertIn('Отправка WB сейчас выключена',text)
        self.assertIn('Пауза WB',text)
        self.assertIn('МСК',text)
    def test_duplicate_confirmation(self):
        nonce=self.selected();self.handle('ok.'+nonce,'confirm')
        self.assertTrue(self.handle('ok.'+nonce,'confirm')['duplicate']);self.assertEqual(self.repo.count('intents'),1)
    def test_second_click_new_event(self):
        nonce=self.selected();self.handle('ok.'+nonce,'confirm')
        with self.assertRaises(Rejected):self.handle('ok.'+nonce,'confirm2')
    def test_old_nonce(self):
        nonce=self.selected();self.handle('v1','new-selection')
        with self.assertRaises(Rejected):self.handle('ok.'+nonce,'confirm')
    def test_repeated_same_choice_preserves_visible_confirmation(self):
        nonce=self.selected()
        self.handle('v2','second-selection')
        self.assertEqual(self.repo.get('cards',self.token)['nonce'],nonce)
        result=self.handle('ok.'+nonce,'confirm')
        self.assertEqual(result['result']['decision'],'approved')
        self.assertEqual(self.repo.count('intents'),1)
    def test_back_invalidates_nonce(self):
        nonce=self.selected();self.handle('back','back')
        with self.assertRaises(Rejected):self.handle('ok.'+nonce,'confirm')
    def test_hold(self):
        self.handle('hold')
        with self.assertRaises(Rejected):self.handle('v1','later')
        self.assertEqual(self.repo.count('intents'),0)
    def test_rework(self):
        self.handle('edit');self.a.record_edit(self.token,11,22,101,'Уточнить модель')
        with self.assertRaises(Rejected):self.handle('v1','later')
        self.assertEqual(self.repo.count('intents'),0)
    def test_new_version_invalidates_old(self):
        self.a.create('token_1','feedbacks','review','v2',self.source,['Новый один','Новый два'],102)
        with self.assertRaises(Rejected):self.handle('v1')
    def test_same_version_mutation(self):
        with self.assertRaises(Rejected):self.a.create('token_1','feedbacks','review','v1',self.source,['Иное','Другое'],102)
    def test_expired(self):
        self.now+=86401
        with self.assertRaises(Rejected):self.handle('v1')
    def test_checksum(self):
        with self.repo.transaction():
            c=self.repo.get('cards',self.token);c['texts'][0]='tampered';self.repo.put('cards',self.token,c)
        with self.assertRaises(Rejected):self.handle('v1')
    def test_disabled(self):
        self.a.enabled=False
        with self.assertRaises(Rejected):self.handle('v1')
    def test_wrong_secret(self):
        with self.assertRaises(Rejected):self.a.handle(self.update('v1'),'wrong')
    def test_wrong_owner(self):
        u=self.update('v1');u['callback_query']['from']['id']=99
        with self.assertRaises(Rejected):self.a.handle(u,'secret')
    def test_wrong_chat(self):
        u=self.update('v1');u['callback_query']['message']['chat']['id']=99
        with self.assertRaises(Rejected):self.a.handle(u,'secret')
    def test_wrong_message(self):
        u=self.update('v1');u['callback_query']['message']['message_id']=99
        with self.assertRaises(Rejected):self.a.handle(u,'secret')
    def test_wrong_bot(self):
        u=self.update('v1');u['callback_query']['message']['from']['id']=99
        with self.assertRaises(Rejected):self.a.handle(u,'secret')
    def test_group(self):
        u=self.update('v1');u['callback_query']['message']['chat']['type']='group'
        with self.assertRaises(Rejected):self.a.handle(u,'secret')
    def test_external_states_block(self):
        for status in ('held','sent','uncertain','publishing'):
            self.a.set_item_state(identity('token_1','feedbacks','review'),status,'canonical')
            with self.assertRaises(Rejected):self.handle('v1',status)
    def test_other_cabinet_is_independent(self):
        self.a.set_item_state(identity('token_2','feedbacks','review'),'held','owner')
        self.handle('v1')
    def test_callback_size(self):
        for row in self.view['reply_markup']['inline_keyboard']:
            for b in row:self.assertLessEqual(len(b['callback_data'].encode()),64)
    def test_receiver_methods_only_edit_ack(self):
        self.receiver.receive(self.update('v1'),'secret')
        self.assertEqual([m for m,p in self.tg.calls],['editMessageText','answerCallbackQuery'])
    def test_delivery_failure_preserves_decision(self):
        nonce=self.selected();self.tg.fail=True
        result=self.receiver.receive(self.update('ok.'+nonce,'confirmed'),'secret')
        self.assertEqual(result['ui_delivery'],'uncertain');self.assertEqual(self.repo.count('intents'),1)
        self.receiver.receive(self.update('ok.'+nonce,'confirmed'),'secret')
        self.assertEqual(self.repo.count('intents'),1)
    def test_incomplete_canonical_read_blocks(self):
        self.receiver.reconcile=lambda c:False
        with self.assertRaises(Rejected):self.receiver.receive(self.update('v1'),'secret')
        self.assertEqual(self.repo.count('events'),0)
    def test_no_legacy_commands(self):
        self.assertTrue(self.receiver.receive({'message':{'text':'остатки'}},'secret')['ignored'])
        self.assertEqual(self.tg.calls,[])
    def test_rework_reply(self):
        self.handle('edit')
        result=self.receiver.receive({'message':{'from':{'id':11},'chat':{'id':22,'type':'private'},
            'reply_to_message':{'message_id':101,'from':{'id':33}},'text':'Сократить'}},'secret')
        self.assertEqual(result['status'],'revision_requested')
    def test_restart_readback(self):
        nonce=self.selected();r=self.handle('ok.'+nonce,'confirm')
        reopened=Repository(self.conn)
        self.assertEqual(reopened.get('intents',r['result']['intent_id'])['answer'],'Ответ два')
    def test_wsgi(self):
        raw=json.dumps(self.update('v1')).encode();statuses=[]
        self.receiver.wsgi({'REQUEST_METHOD':'POST','CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw),
            'HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN':'secret'},lambda s,h:statuses.append(s))
        self.assertEqual(statuses,['200 OK'])
    def test_transport_rejects_legacy_send(self):
        transport=TelegramTransport('dummy',opener=lambda *a,**k: self.fail('Network called'))
        with self.assertRaises(ValueError):transport.call('sendMessage',{})
    def test_transport_request(self):
        requests=[]
        def opener(request,timeout):
            requests.append(request)
            return io.BytesIO(b'{"ok":true,"result":true}')
        transport=TelegramTransport('dummy',opener=opener)
        self.assertTrue(transport.call('answerCallbackQuery',{'callback_query_id':'x'}))
        self.assertEqual(json.loads(requests[0].data),{'callback_query_id':'x'})
    def test_transport_error_sanitized(self):
        def opener(*a,**k):raise RuntimeError('https://botSECRET')
        with self.assertRaisesRegex(RuntimeError,'^Telegram transport unconfirmed$'):
            TelegramTransport('SECRET',opener=opener).call('answerCallbackQuery',{})
    def test_canonical_manual_answer(self):
        card=self.repo.get('cards',self.token)
        guard=CanonicalGuard(self.a,lambda c:dict(complete=True,ref=c['ref'],answered=True))
        self.assertFalse(guard(card));self.assertEqual(self.repo.get('items',card['ref'])['status'],'sent')
    def test_canonical_ishkhan_hold(self):
        token,_=self.a.create('token_2','feedbacks','PwB5eXmFztbgyBhGctsP','v1',self.source,['A','B'],102)
        card=self.repo.get('cards',token)
        guard=CanonicalGuard(self.a,lambda c:dict(complete=True,ref=c['ref'],hold=True))
        self.assertFalse(guard(card))
        self.assertEqual(self.repo.get('items',card['ref'])['status'],'held')
        self.handle('v1')  # OOO remains independent.
    def test_canonical_missing_fields(self):
        card=self.repo.get('cards',self.token)
        self.assertFalse(CanonicalGuard(self.a,lambda c:dict(complete=True,ref=c['ref']))(card))
    def test_canonical_changed_version(self):
        from review_telegram_approval import sha
        card=self.repo.get('cards',self.token)
        state=dict(complete=True,ref=card['ref'],hold=False,answered=False,publication_state='idle',version='v2',hashes=card['hashes'],source_sha256=sha(card['source']))
        self.assertFalse(CanonicalGuard(self.a,lambda c:state)(card))
    def test_canonical_exact_version(self):
        from review_telegram_approval import sha
        card=self.repo.get('cards',self.token)
        state=dict(complete=True,ref=card['ref'],hold=False,answered=False,publication_state='idle',version=card['version'],hashes=card['hashes'],source_sha256=sha(card['source']))
        self.assertTrue(CanonicalGuard(self.a,lambda c:state)(card))
    def test_disk_restart_retains_approval(self):
        with tempfile.TemporaryDirectory(dir=os.path.dirname(__file__)) as directory:
            path=os.path.join(directory,'approvals.sqlite')
            conn=sqlite3.connect(path);repo=Repository(conn);repo.setup()
            a=Approval(repo,'secret',11,22,33,enabled=True)
            token,_=a.create('token_1','feedbacks','review','v1',self.source,['A','B'],101)
            self.token=token
            a.handle(self.update('v2','select'),'secret')
            nonce=repo.get('cards',token)['nonce']
            result=a.handle(self.update('ok.'+nonce,'confirm'),'secret');conn.close()
            conn=sqlite3.connect(path);repo=Repository(conn)
            self.assertEqual(repo.get('intents',result['result']['intent_id'])['answer'],'B')
            self.assertEqual(repo.count('events'),2);conn.close()
    def test_concurrent_confirmations_one_intent(self):
        with tempfile.TemporaryDirectory(dir=os.path.dirname(__file__)) as directory:
            path=os.path.join(directory,'approvals.sqlite')
            conn=sqlite3.connect(path);repo=Repository(conn);repo.setup()
            a=Approval(repo,'secret',11,22,33,enabled=True)
            token,_=a.create('token_1','feedbacks','review','v1',self.source,['A','B'],101)
            self.token=token;a.handle(self.update('v1','select'),'secret')
            nonce=repo.get('cards',token)['nonce'];conn.close()
            def confirm(event):
                connection=sqlite3.connect(path,timeout=5)
                try:
                    worker=Approval(Repository(connection),'secret',11,22,33,enabled=True)
                    worker.handle(self.update('ok.'+nonce,event),'secret');return 'approved'
                except Rejected:return 'rejected'
                finally:connection.close()
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(confirm,['click1','click2']))
            self.assertEqual(sorted(results),['approved','rejected'])
            conn=sqlite3.connect(path);self.assertEqual(Repository(conn).count('intents'),1);conn.close()

if __name__=='__main__':unittest.main(verbosity=2)
