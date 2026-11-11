"""Morning recovery must retain full-check guards without model calls."""
import unittest
from china_morning_rules_review import review,enabled,POLICY
class IO:
 def __init__(self,allow=True):self.allow=allow
 def get(self,key):
  if key!=POLICY:raise AssertionError('Unexpected model/backend read')
  return dict(enabled=self.allow,mode='full_checks_no_model',cabinet='token_3',chat_id=-1004342917488,owner_id=5122667182,paid_api_allowed=False)
def fixture():
 return dict(economic_review_complete=True,campaigns=[],recommendation_directions={x:{}for x in ['raise','add','reduce','exclude']}),dict(day_quality=dict(usable=True),period_to='2026-11-10',full_growth_review=dict(status='complete',input_key='private-source'))
class MorningReview(unittest.TestCase):
 def test_no_model_and_explicit_provenance(self):
  b,s=fixture();v=review(IO(),b,s);self.assertEqual(v['morning_review']['model_calls'],0);self.assertNotIn('codex_analysis',v);self.assertNotIn('morning_review',b)
 def test_missing_economics_blocks(self):
  b,s=fixture();b['economic_review_complete']=False
  with self.assertRaisesRegex(ValueError,'Economic'):review(IO(),b,s)
 def test_incomplete_catalogue_blocks(self):
  b,s=fixture();s['full_growth_review']['status']='partial'
  with self.assertRaisesRegex(ValueError,'catalogue'):review(IO(),b,s)
 def test_rejected_day_blocks(self):
  b,s=fixture();s['day_quality']['usable']=False
  with self.assertRaises(ValueError):review(IO(),b,s)
 def test_no_implicit_policy(self):
  b,s=fixture()
  with self.assertRaises(ValueError):review(IO(False),b,s)
 def test_unready_action_blocks(self):
  b,s=fixture();b['campaigns']=[dict(focus=[dict(action={'id':'x'},pending_first_day=True)])]
  with self.assertRaisesRegex(ValueError,'Unready'):review(IO(),b,s)
if __name__=='__main__':unittest.main()
