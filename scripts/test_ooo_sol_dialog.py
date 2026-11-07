import unittest
from unittest.mock import patch
from ooo_sol_dialog import eligible,CHAT,BOT,Worker
class Tests(unittest.TestCase):
 def msg(self):return {'update_id':1,'message':{'message_id':2,'date':100,'chat':{'id':CHAT},'from':{'id':3},'text':'Агент, объясни отчёт'}}
 def test_only_new_group_addressed_human_messages(self):
  u=self.msg();self.assertTrue(eligible(u,{'not_before_unix':99}));self.assertFalse(eligible(u,{'not_before_unix':101}))
  u['message']['chat']['id']=1;self.assertFalse(eligible(u,{'not_before_unix':99}))
  u=self.msg();u['message']['from']['is_bot']=True;self.assertFalse(eligible(u,{'not_before_unix':99}))
 def test_foreign_commands_and_ordinary_chatter_ignored(self):
  for text in ['/ask@otherbot test','/confirm 123','Привет, Павел']:
   u=self.msg();u['message']['text']=text;self.assertFalse(eligible(u,{'not_before_unix':99}))
 def test_reply_to_our_bot_is_addressed(self):
  u=self.msg();u['message']['text']='А почему?';u['message']['reply_to_message']={'from':{'id':BOT}}
  self.assertTrue(eligible(u,{'not_before_unix':99}))
 def test_open_group_accepts_new_plain_text_without_an_address(self):
  u=self.msg();u['message']['text']='Почему выросли расходы?'
  p={'not_before_unix':90,'open_group_dialogue':True,'open_text_not_before_unix':99}
  self.assertTrue(eligible(u,p))
  u['message']['date']=98;self.assertFalse(eligible(u,p))
 def test_open_group_still_rejects_foreign_commands_bots_and_other_chats(self):
  p={'not_before_unix':90,'open_group_dialogue':True}
  for text in ['/confirm 123','/ask@otherbot test','@otherbot test']:
   u=self.msg();u['message']['text']=text;self.assertFalse(eligible(u,p))
  u=self.msg();u['message']['from']['is_bot']=True;self.assertFalse(eligible(u,p))
 def test_uncertain_send_is_not_repeated(self):
  class DB:
   def __init__(self):self.v={}
   def update(self,k,v):self.v[k]=v.copy()
  db=DB();w=Worker(db);w.context=lambda m:'evidence';calls=[]
  def tg(method,body):
   calls.append(method)
   if method=='getChatMember':return {'status':'member'}
   raise TimeoutError()
  w.tg=tg;entry={'status':'queued','update_id':1,'message':self.msg()['message']}
  with patch('ooo_sol_dialog.BoundedSol')as model:
   model.return_value.answer.return_value='Ответ'
   with self.assertRaises(TimeoutError):w.process('key',entry)
   self.assertEqual(w.process('key',db.v['key']),'send_uncertain')
   self.assertEqual(model.return_value.answer.call_count,1)
  self.assertEqual(calls.count('sendMessage'),1)
 def test_nonmember_never_reaches_model(self):
  w=Worker(object());w.tg=lambda *a:{'status':'left'}
  with patch('ooo_sol_dialog.BoundedSol')as model:
   with self.assertRaises(PermissionError):w.process('key',{'status':'queued','update_id':1,'message':self.msg()['message']})
   model.assert_not_called()
 def test_question_from_old_group_never_reaches_model(self):
  w=Worker(object());u=self.msg();u['message']['chat']['id']=-5459387392
  with patch('ooo_sol_dialog.BoundedSol')as model:
   with self.assertRaises(PermissionError):w.process('key',{'status':'queued','update_id':None,'message':u['message']})
   model.assert_not_called()
if __name__=='__main__':unittest.main()
