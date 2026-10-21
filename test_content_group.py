import sys,sqlite3,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_telegram_approval import Approval,Repository,Rejected
from review_telegram_receiver import Receiver

class Telegram:
 def __init__(self):self.members={20,21};self.calls=[]
 def call(self,method,payload):
  self.calls.append((method,payload))
  if method=='getChatMember':return {'user':{'id':payload['user_id']},'status':'member' if payload['user_id'] in self.members else 'left'}
  return True

class GroupApprovalTests(unittest.TestCase):
 def setUp(self):
  self.repo=Repository(sqlite3.connect(':memory:'));self.repo.setup()
  self.a=Approval(self.repo,'secret',1,1,99,enabled=True)
  self.a.group={'enabled':True,'destination_verified':True,'chat_id':-1001}
  self.a.chat='-1001';self.tg=Telegram();self.receiver=Receiver(self.a,self.tg,lambda c:True)
  self.source=dict(buyer='Покупатель',rating=4,text='Отзыв',pros='',cons='',article='bag')
  self.token,_=self.a.create('token_1','feedbacks','review','v1',self.source,['Ответ один','Ответ два'],5)
 def update(self,actor=20,chat=-1001,mid=5,action='p1',qid='one'):
  return {'update_id':1,'callback_query':{'id':qid,'from':{'id':actor,'is_bot':False},'message':{'message_id':mid,'chat':{'id':chat,'type':'supergroup'},'from':{'id':99}},'data':'rv1:'+self.token+':'+action}}
 def test_member_approval_retains_actor_and_immutable_intent(self):
  result=self.receiver.receive(self.update(),'secret');intent=self.repo.get('intents',result['result']['intent_id'])
  self.assertEqual(intent['approved_by_user_id'],'20');self.assertEqual(intent['owner_id'],'1');self.assertEqual(intent['chat_id'],'-1001')
  self.receiver.receive(self.update(actor=21,qid='two'),'secret');self.assertEqual(self.repo.count('intents'),1)
 def test_nonmember_rejected(self):
  with self.assertRaises(Rejected):self.receiver.receive(self.update(actor=22),'secret')
  self.assertEqual(self.repo.count('intents'),0)
 def test_foreign_chat_and_wrong_message_rejected(self):
  for chat,mid in [(-1002,5),(-1001,6)]:
   with self.assertRaises(Rejected):self.receiver.receive(self.update(chat=chat,mid=mid),'secret')
  self.assertEqual(self.repo.count('intents'),0)
 def test_group_message_cannot_approve_old_private_card(self):
  self.a.chat='1';token,_=self.a.create('token_2','feedbacks','private','v1',self.source,['A','B'],5)
  self.token=token
  with self.assertRaises(Rejected):self.receiver.receive(self.update(),'secret')
 def test_departed_member_cannot_edit(self):
  self.receiver.receive(self.update(action='edit'),'secret');self.tg.members.remove(20)
  edit={'message':{'message_id':6,'chat':{'id':-1001,'type':'supergroup'},'from':{'id':20},'text':'Изменить','reply_to_message':{'message_id':5,'from':{'id':99}}}}
  with self.assertRaises(Rejected):self.receiver.receive(edit,'secret')
 def test_member_revision_is_returned_for_group_confirmation(self):
  from types import SimpleNamespace
  from unittest.mock import Mock,patch
  from review_telegram_approval import sha
  from review_approval_revision import revise
  self.receiver.receive(self.update(action='edit'),'secret')
  answer='Добрый день! Спасибо за подробный отзыв о нашей сумке. С уважением, команда VESCHI'
  event=self.a.record_edit(self.token,20,-1001,5,answer)
  raw={'id':'review','text':'Отзыв'}
  with self.repo.transaction():
   card=self.repo.get('cards',self.token);card['binding']={'draft_key':'draft','raw_source_sha256':sha(raw)};self.repo.put('cards',self.token,card)
  source=SimpleNamespace(read=lambda key:{'source_sha256':sha(raw)},matching=lambda *args:[{'version':'v1','item':raw}])
  bridge=SimpleNamespace(source=source,draft_key=lambda *args:'revised-draft')
  store=SimpleNamespace(insert=lambda *args:None)
  with patch.dict(sys.modules,{'validator':SimpleNamespace(validate_answer=lambda *args:{'valid':True})}),patch('review_approval_revision.NewNotice') as notice:
   notice.return_value.deliver.return_value={'status':'confirmed'}
   result=revise(self.a,bridge,store,self.tg,event['revision_event_id'],lambda:None,0)
  self.assertEqual(result['status'],'confirmed');self.assertEqual(self.a.chat,'-1001');self.assertEqual(self.repo.get('events',event['revision_event_id'])['actor'],'20')
 def test_legacy_intent_problem_goes_to_group(self):
  from review_approval_card_delivery import notify_owner_problem,notify_owner_receipt
  self.a.chat='1'
  token,_=self.a.create('token_2','feedbacks','legacy','v1',self.source,['A','B'],8)
  update={'callback_query':{'id':'legacy','from':{'id':1},'message':{'message_id':8,'chat':{'id':1,'type':'private'},'from':{'id':99}},'data':'rv1:'+token+':p1'}}
  result=self.a.handle(update,'secret');intent=self.repo.get('intents',result['result']['intent_id']);intent['status']='blocked'
  calls=[]
  class Notices:
   def call(_,method,payload):
    calls.append((method,payload));return {'message_id':100+len(calls),'chat':{'id':int(payload['chat_id'])}}
  self.assertEqual(notify_owner_problem(self.a,Notices(),intent)['chat_id'],'-1001')
  self.assertEqual(notify_owner_receipt(self.a,Notices(),intent)['chat_id'],'-1001')
  self.assertTrue(all(str(payload['chat_id'])=='-1001' for _,payload in calls))
 def test_production_delivery_never_falls_back_to_private(self):
  self.assertEqual(self.a.delivery_chat(),'-1001')
  self.a.group['enabled']=False;self.repo.pg=True
  try:
   with self.assertRaises(Rejected):self.a.delivery_chat()
  finally:self.repo.pg=False

if __name__=='__main__':unittest.main()
