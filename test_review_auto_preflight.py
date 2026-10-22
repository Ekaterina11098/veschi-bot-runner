import unittest
from unittest.mock import Mock
from review_auto_five_star import validate_preflight_response
from review_approval_executor import AutomaticPolicyChanged

class PreflightScopeTests(unittest.TestCase):
 def setUp(self):
  self.intent=dict(authorization_channel='automatic_policy',kind='feedbacks',status='awaiting_preflight',item_id='review-a')
  self.url='https://feedbacks-api.wildberries.ru/api/v1/feedback'
 def response(self,body,status=200):
  r=Mock(status_code=status);r.json.return_value=body;return r
 def test_supabase_cache_list_is_not_wb_review(self):
  r=self.response([{'payload':{'until':123}}])
  validate_preflight_response(self.intent,'GET','https://db.supabase.co/rest/v1/telegram_api_cache',r)
  r.json.assert_not_called()
 def test_non_wb_and_other_methods_never_qualify(self):
  for method,url,status in [('POST',self.url,200),('GET',self.url,429),('GET','https://feedbacks-api.wildberries.ru/api/v1/question',200),('GET','https://api.telegram.org/bot-not-a-token/getChat',200)]:
   r=self.response([],status)
   validate_preflight_response(self.intent,method,url,r);r.json.assert_not_called()
 def test_malformed_wb_success_fails_closed(self):
  for body in ([],None,{'data':{'id':'wrong'}},{'data':{'id':'review-a','answer':'broken'}}):
   with self.subTest(body=body),self.assertRaises(RuntimeError):
    validate_preflight_response(self.intent,'GET',self.url,self.response(body))
 def test_changed_fresh_review_requires_manual_approval(self):
  r=self.response({'data':{'id':'review-a','productValuation':5,'text':'Молния сломалась'}})
  with self.assertRaises(AutomaticPolicyChanged):validate_preflight_response(self.intent,'GET',self.url,r)
 def test_eligible_and_existing_answer_read_only_reconciliation(self):
  for item in ({'id':'review-a','productValuation':5,'text':''},{'id':'review-a','productValuation':1,'answer':{'text':'Already present'}}):
   validate_preflight_response(self.intent,'GET',self.url,self.response({'data':item}))
 def test_manual_and_verify_intents_not_reclassified(self):
  for updates in ({'authorization_channel':'telegram'},{'status':'verify'}):
   r=self.response([])
   validate_preflight_response(dict(self.intent,**updates),'GET',self.url,r);r.json.assert_not_called()
if __name__=='__main__':unittest.main()
