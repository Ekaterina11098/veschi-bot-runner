"""End-to-end owner confirmation to WB readback and Telegram receipts, no network."""
import sqlite3,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_telegram_approval import Approval,Repository,sha
from review_telegram_receiver import Receiver
from review_approval_executor import Executor
from review_approval_card_delivery import notify_owner_receipt

class AutonomyTests(unittest.TestCase):
    def test_full_pipeline_all_cabinets_both_kinds_and_repeated_click(self):
        for cabinet in ('token_1','token_2','token_3'):
            for kind in ('feedbacks','questions'):
                with self.subTest(cabinet=cabinet,kind=kind):
                    repo=Repository(sqlite3.connect(':memory:'));repo.setup()
                    a=Approval(repo,'secret','owner','chat','bot',enabled=True,clock=lambda:1000)
                    token,_=a.create(cabinet,kind,'same-id','v1',dict(buyer='Имя',rating=0 if kind=='questions' else 5,text='Текст',pros='',cons='',article='sku'),['Первый ответ','Второй ответ'],10)
                    telegram=Mock();telegram.call.return_value=True
                    rx=Receiver(a,telegram,lambda c:True,preserve=lambda:None)
                    def cb(event,action):
                        return {'callback_query':{'id':event,'from':{'id':'owner'},'data':'rv1:'+token+':'+action,'message':{'message_id':10,'from':{'id':'bot'},'chat':{'id':'chat','type':'private'}}}}
                    rx.receive(cb('select','v2'),'secret');self.assertEqual(repo.count('intents'),0)
                    nonce=repo.get('cards',token)['nonce']
                    result=rx.receive(cb('confirm','ok.'+nonce),'secret')
                    intent_id=result['result']['intent_id'];posts=[];actual=[''];saved=[]
                    def post(i):
                        self.assertEqual(repo.get('intents',intent_id)['status'],'verify')
                        posts.append((i['cabinet'],i['kind'],i['answer']));actual[0]=i['answer']
                    adapter=SimpleNamespace(pause=lambda c:0,read=lambda i:actual[0],post=post)
                    executor=Executor(a,lambda c:True,adapter,enabled=True,preserve=lambda:saved.append(repo.get('intents',intent_id)['status']))
                    result=executor.run(intent_id)
                    self.assertEqual(result['status'],'confirmed')
                    self.assertEqual(result['actual_answer_sha256'],sha('Второй ответ'))
                    self.assertEqual(posts,[(cabinet,kind,'Второй ответ')]);self.assertIn('verify',saved)
                    executor.run(intent_id);self.assertEqual(len(posts),1)
                    delayed=a.handle(cb('later-click','ok.'+nonce),'secret')
                    self.assertTrue(delayed['duplicate']);self.assertEqual(repo.count('intents'),1)
                    telegram.call.reset_mock();telegram.call.return_value={'chat':{'id':'chat'},'message_id':50}
                    self.assertEqual(notify_owner_receipt(a,telegram,result)['status'],'suppressed')
                    notify_owner_receipt(a,telegram,result);self.assertTrue(all(call.args[0]=='deleteMessage' for call in telegram.call.call_args_list))
    def test_receipts_do_not_claim_acceptance_for_uncertain_or_blocked(self):
        for state,word in [('blocked','Требуется ваша проверка'),('manual_present','уже есть другой ответ')]:
            repo=Repository(sqlite3.connect(':memory:'));repo.setup();a=Approval(repo,'s','owner','chat','bot')
            i=dict(id=state,owner_id='owner',chat_id='chat',card_token='c',cabinet='token_1',kind='questions',item_id='q',status=state)
            repo.put('intents',state,i);repo.put('cards','c',{'source':{'article':'sku'}});repo.conn.commit()
            tg=Mock();tg.call.return_value={'chat':{'id':'chat'},'message_id':12}
            notify_owner_receipt(a,tg,i)
            self.assertIn(word,tg.call.call_args[0][1]['text'])
            self.assertNotIn('Подтверждение принято',tg.call.call_args[0][1]['text'])
if __name__=='__main__':unittest.main()
