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

if __name__=='__main__':unittest.main()
