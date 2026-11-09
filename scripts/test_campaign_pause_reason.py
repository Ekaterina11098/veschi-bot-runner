import unittest
from china_campaign_pause_reason import classify,attach_previous

class PauseTests(unittest.TestCase):
 def setUp(self):self.state=dict(id=1,status=11,timestamps=dict(started='2026-11-08T06:00:00+00:00'))
 def test_zero_balance_alone_is_not_budget_cause(self):self.assertEqual(classify(self.state,0)['cause'],'unknown')
 def test_owner_command_overrides_budget_transition(self):
  r=dict(cache_key='canonical',payload=dict(status='verified',owner_id=5122667182,kind='pause_campaign',after=dict(id=1,status=11),verified_at='2026-11-08T20:00:00+00:00'))
  self.assertEqual(classify(self.state,0,[r],dict(status=9,balance=1))['cause'],'owner_paused')
 def test_unverified_or_old_manual_command_not_used(self):
  for status,when in [('accepted','2026-11-08T20:00:00+00:00'),('verified','2026-11-07T20:00:00+00:00')]:
   r=dict(status=status,owner_id=5122667182,kind='pause_campaign',after=dict(id=1,status=11),verified_at=when)
   self.assertEqual(classify(self.state,0,[r])['cause'],'unknown')
 def test_funding_or_exclusion_readback_not_pause_command(self):
  r=dict(status='verified',owner_id=5122667182,after=dict(id=1,status=11),amount_cny=100,verified_at='2026-11-08T20:00:00+00:00')
  self.assertEqual(classify(self.state,100,[r])['cause'],'unknown')
 def test_zero_transition_is_probable_not_verified_cause(self):
  r=classify(self.state,0,previous=dict(status=9,balance=0,source_key='before'))
  self.assertEqual(r['cause'],'budget_exhaustion_observed');self.assertEqual(r['confidence'],'probable')
 def test_surviving_pause_preserves_evidence(self):
  old=dict(cause='budget_exhaustion_observed',confidence='probable',before_source='exact')
  self.assertEqual(classify(self.state,0,previous=dict(status=11,balance=0),previous_audit=old),old)
 def test_active_clears_pause_class(self):
  self.state['status']=9;self.assertEqual(classify(self.state,0)['cause'],'not_paused')
 def test_saved_transition_invalidated_by_later_restart(self):
  t=dict(state_started_at=self.state['timestamps']['started'],before_status=9,after_status=11,after_balance=0,source_keys=['before','after'],observed_at='2026-11-08T20:00:00+00:00')
  self.assertEqual(classify(self.state,0,transition=t)['cause'],'budget_exhaustion_observed')
  self.state['timestamps']['started']='2026-11-09T08:00:00+00:00'
  self.assertEqual(classify(self.state,0,transition=t)['cause'],'unknown')
 def test_old_manual_pause_superseded_by_observed_active_state(self):
  r=dict(status='verified',owner_id=5122667182,kind='pause_campaign',after=dict(id=1,status=11),verified_at='2026-11-08T10:00:00+00:00')
  before=dict(status=9,balance=0,observed_at='2026-11-08T19:00:00+00:00')
  self.assertEqual(classify(self.state,0,[r],before)['cause'],'budget_exhaustion_observed')

if __name__=='__main__':unittest.main()
