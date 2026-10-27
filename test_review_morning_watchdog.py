import unittest
from datetime import datetime,timezone
from review_morning_watchdog import choose
class MorningRecovery(unittest.TestCase):
 def setUp(self):
  self.now=datetime(2026,10,27,6,tzinfo=timezone.utc)
  self.cfg=dict(enabled=True,new_notices_enabled=True,destination_verified=True)
  self.complete=dict(status='complete',scopes={c:dict(status='complete') for c in ('token_1','token_2','token_3')})
 def test_missing_trigger(self):self.assertEqual(choose(self.now,self.cfg,{},{}),'reviews')
 def test_active_either_kind(self):
  for k in ('reviews','questions'):
   self.assertIsNone(choose(self.now,self.cfg,{}, {k:[dict(status='queued')]}))
 def test_questions_follow_reviews(self):self.assertEqual(choose(self.now,self.cfg,{'reviews':self.complete},{}),'questions')
 def test_partial_resume_after_both_started(self):self.assertEqual(choose(self.now,self.cfg,{'reviews':{'status':'collecting'},'questions':self.complete},{}),'reviews')
 def test_first_turn_fairness(self):self.assertEqual(choose(self.now,self.cfg,{'reviews':{'status':'collecting'}},{}),'questions')
 def test_all_cabinets_required(self):self.assertEqual(choose(self.now,self.cfg,{'reviews':dict(status='complete',scopes={}), 'questions':self.complete},{}),'reviews')
 def test_done(self):self.assertIsNone(choose(self.now,self.cfg,{'reviews':self.complete,'questions':self.complete},{}))
 def test_disabled(self):self.assertIsNone(choose(self.now,{}, {},{}))
 def test_outside_window(self):self.assertIsNone(choose(self.now.replace(hour=12),self.cfg,{},{}))
 def test_unknown_dispatch_cooldown(self):self.assertIsNone(choose(self.now,self.cfg,{}, {},self.now.timestamp()-60))
if __name__=='__main__':unittest.main()
