import copy,importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('rules',Path(__file__).with_name('china_midday_rules_review.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class RulesReview(unittest.TestCase):
 def source(self):return dict(day_quality=dict(usable=True),full_growth_review=dict(status='complete',input_key='dated:source'),period_to='2026-11-10')
 def bundle(self):return dict(economic_review_complete=True,campaigns=[dict(id=1,focus=[dict(action=dict(id='exact',target_minor=21))],attention=[])],recommendation_directions={d:dict(status='checked')for d in ('raise','add','reduce','exclude')})
 def test_complete_review_keeps_exact_checked_actions_without_model(self):
  b=self.bundle();out=m.review(b,self.source());self.assertEqual(b['campaigns'],out['campaigns']);self.assertEqual(0,out['midday_review']['model_calls']);self.assertNotIn('midday_review',b)
 def test_incomplete_economics_cannot_pass(self):
  b=self.bundle();b['economic_review_complete']=False
  with self.assertRaisesRegex(ValueError,'Economic'):m.review(b,self.source())
 def test_partial_catalogue_cannot_pass(self):
  s=self.source();s['full_growth_review']['status']='collecting'
  with self.assertRaisesRegex(ValueError,'catalogue'):m.review(self.bundle(),s)
 def test_pending_action_cannot_pass(self):
  b=self.bundle();b['campaigns'][0]['focus'][0]['pending_first_day']=True
  with self.assertRaisesRegex(ValueError,'Unready'):m.review(b,self.source())
 def test_all_four_directions_required(self):
  b=self.bundle();b['recommendation_directions'].pop('add')
  with self.assertRaisesRegex(ValueError,'four'):m.review(b,self.source())
 def test_scoped_policy_does_not_disable_telegram_dialogue(self):
  p=dict(enabled=True,mode='full_checks_no_model',cabinet='token_3',chat_id=-1004342917488,owner_id=5122667182,paid_api_allowed=False)
  class IO:
   def get(self,key):return p if key==m.POLICY else None
  self.assertTrue(m.enabled(IO()));p['paid_api_allowed']=True;self.assertFalse(m.enabled(IO()))
if __name__=='__main__':unittest.main()