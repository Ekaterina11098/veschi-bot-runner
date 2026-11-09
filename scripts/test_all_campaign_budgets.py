import copy,unittest
from china_budget_reserve import apply,attach_completed_evidence,hourly_audit
from china_budget_page_actions import owner_policy,page_action
from china_advertising_v2_png import budget_column

def campaign(cid=1,status=9,balance=100):
 return dict(id=cid,name='test',status=status,balance=balance,period=None,last=None,budget_members=[dict(nm=2)],budget_period=dict(spend=30,amount=1000,orders=5),campaign_budget_economics=dict(status='positive',ready=True,reason='preliminary',observed_at='2026-11-09T08:20:00+00:00'))
def bundle(*cs):
 return dict(campaigns=list(cs),budget_days=['2026-11-06','2026-11-07','2026-11-08'],budget_observed_at='2026-11-09T08:22:00+00:00',budget_balance_observed_at_iso='2026-11-09T08:22:00+00:00')
class Tests(unittest.TestCase):
 def test_paused_zero_never_disappears_or_restarts(self):
  c=campaign(status=11,balance=0);c['budget_reference_need']=300.72
  b=apply(bundle(c));c=b['campaigns'][0]
  self.assertEqual(c['budget_audit_state'],'paused_zero');self.assertTrue(c['budget_review_required']);self.assertIsNone(page_action(c,b));self.assertIn('причина паузы',budget_column(c))
  self.assertIsNone(c.get('budget_reference_need'))
 def test_all_states_are_accounted(self):
  cs=[campaign(i,s)for i,s in enumerate([4,9,11,7],1)]
  b=apply(bundle(*cs));self.assertEqual(len(b['budget_audit']),4);self.assertTrue(b['budget_audit_coverage']['complete'])
  self.assertEqual([c['budget_audit_state']for c in b['campaigns']],['draft_review','covered','paused_review','archived'])
 def test_owner_hold_survives_renderer_reapply(self):
  class IO:
   def get(self,key):return {'do_not_fund':{'1':'owner hold'}}
  b=apply(owner_policy(IO(),apply(bundle(campaign(balance=0)))))
  self.assertEqual(b['budget_audit']['1']['status'],'owner_hold');self.assertFalse(b['campaigns'][0]['budget_review_required']);self.assertIsNone(page_action(b['campaigns'][0],b))
 def test_launch_day_spend_is_not_full_reserve(self):
  c=campaign(balance=89);c['budget_started_at']='2026-11-08T09:58:00+03:00'
  b=apply(bundle(c));c=b['campaigns'][0]
  self.assertEqual(c['budget_audit_state'],'starter_review');self.assertIsNone(c['budget_reference_need']);self.assertIsNone(page_action(c,b));self.assertIn('трёх полных',budget_column(c))
 def test_missing_or_stale_not_zero_or_covered(self):
  for mutate in [lambda c:c.update(budget_period=None),lambda c:c.update(balance=None)]:
   c=campaign();mutate(c);self.assertEqual(apply(bundle(c))['campaigns'][0]['budget_audit_state'],'data_blocked')
  b=bundle(campaign());b['budget_balance_observed_at_iso']='2026-11-09T05:00:00+00:00';self.assertEqual(apply(b)['campaigns'][0]['budget_audit_state'],'data_blocked')
 def test_waiting_outcome_can_fund_continuation(self):
  c=campaign(balance=0);c['campaign_budget_economics']['evaluation_status']='waiting'
  b=apply(bundle(c));self.assertEqual(b['campaigns'][0]['budget_action']['amount_cny'],100)
 def test_zero_orders_not_zero_drr_and_not_auto_fund(self):
  c=campaign(balance=0);c['budget_period'].update(amount=0,orders=0);c['campaign_budget_economics']['status']='unknown'
  c=apply(bundle(c))['campaigns'][0];self.assertIsNone(c['budget_drr']);self.assertIsNone(c['budget_action']);self.assertTrue(c['budget_review_required'])
 def test_inventory_missing_fails_instead_of_claiming_all(self):
  s=dict(observed_at='2026-11-09T08:22:00+00:00',period_to='2026-11-08',ids=[1],batches={})
  with self.assertRaisesRegex(ValueError,'inventory coverage'):attach_completed_evidence(bundle(),s,[])
 def test_suppressed_draft_gets_audit_row(self):
  s=dict(observed_at='2026-11-09T08:22:00+00:00',period_to='2026-11-08',ids=[1],batches={'0':dict(campaigns=dict(adverts=[dict(id=1,status=4,settings=dict(name='draft'),nm_settings=[])]),stats=[])})
  b=apply(attach_completed_evidence(bundle(),s,[]));self.assertEqual(b['budget_audit']['1']['status'],'draft_review')
 def test_hourly_missing_source_exposes_each_campaign(self):
  class Cache:
   def get(self,key):return None
  inv=dict(adverts=[dict(status=9,advert_list=[dict(advertId=1)]),dict(status=11,advert_list=[dict(advertId=2)])])
  r=hourly_audit(Cache(),dict(completed_at='2026-11-09T08:22:00+00:00'),inv)
  self.assertEqual(set(r['campaigns']),{'1','2'});self.assertEqual(r['status'],'blocked')
 def test_hourly_rejected_day_cannot_be_ready(self):
  class Cache:
   def get(self,key):return dict(period_to='2026-11-08',day_quality=dict(usable=False))
  self.assertEqual(hourly_audit(Cache(),dict(completed_at='2026-11-09T08:22:00+00:00'),dict(adverts=[]))['status'],'blocked')

if __name__=='__main__':unittest.main()
