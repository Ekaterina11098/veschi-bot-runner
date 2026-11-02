import unittest
from china_owner_reply_guard import resolved,growth_reply
class Guard(unittest.TestCase):
 def test_verified_owner_resolution(self):
  class W:
   def get(self,k):return {'status':'answered_by_owner','chat_id':1,'message_id':637,'receipt_key':'receipt'} if k.endswith(':223') else {'status':'sent','chat_id':1,'message_id':637}
  self.assertIsNotNone(resolved(W(),{'id':223,'chat_id':1}))
  self.assertIsNone(resolved(W(),{'id':223,'chat_id':2}))
 def test_no_unverified_suppression(self):
  class W:
   def get(self,k):return {'status':'answered_by_owner','chat_id':1,'message_id':637,'receipt_key':'r'} if k.endswith(':223') else {'status':'uncertain','chat_id':1,'message_id':637}
  self.assertIsNone(resolved(W(),{'id':223,'chat_id':1}))
 def test_addition_question_not_existing_bid_table(self):
  job={'request_text':'Есть еще товары которые можно добавить в рекламу?'}
  trace=[{'name':'diagnose_article','result':{'rows':[{'action':None,'stage':'missing_data'}]}}]
  a=growth_reply(job,'|123|Нет| HTTP 498',trace)
  self.assertNotIn('498',a);self.assertNotIn('|',a);self.assertIn('пока не завершена',a)
 def test_other_question_preserved(self):
  self.assertEqual(growth_reply({'request_text':'Покажи воронку 123'},'full table',[]),'full table')
 def test_ready_exact_plan_preserved(self):
  trace=[{'name':'prepare_advertising_plan','result':{'status':'ready'}},{'name':'diagnose_article','result':{'rows':[]}}]
  self.assertEqual(growth_reply({'request_text':'Добавь товар в рекламу'},'bound plan',trace),'bound plan')
if __name__=='__main__':unittest.main()
