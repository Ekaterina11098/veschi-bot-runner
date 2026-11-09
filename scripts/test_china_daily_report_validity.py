import unittest
from datetime import datetime,timezone
from china_daily_report_validity import valid,publish,CURRENT
class IO:
 def __init__(self):self.rows={}
 def get(self,k):return self.rows.get(k)
 def put(self,k,v):self.rows[k]=v
class ValidityTests(unittest.TestCase):
 def setUp(self):
  self.io=IO();self.p=dict(plan_id='page-0',family='drr',report_generation='report-a',validity_mode='until_replaced',expires_at='2020-01-01T00:00:00+00:00');publish(self.io,self.p)
 def test_delayed_confirmation_survives_old_clock_expiry(self):self.assertTrue(valid(self.io,self.p,datetime(2030,1,1,tzinfo=timezone.utc)))
 def test_replacement_rejects_old_page_and_selection(self):
  child=dict(self.p,plan_id='selected-job99');publish(self.io,dict(self.p,report_generation='report-b'))
  self.assertFalse(valid(self.io,self.p));self.assertFalse(valid(self.io,child))
 def test_explicit_revocation_blocks(self):self.assertFalse(valid(self.io,dict(self.p,invalidated_at='2026-11-09')))
 def test_all_pages_same_generation_remain_current(self):
  publish(self.io,dict(self.p,plan_id='page-1'));self.assertTrue(valid(self.io,self.p))
 def test_other_family_does_not_revoke(self):
  publish(self.io,dict(self.p,family='budgets',report_generation='budgets-b'));self.assertTrue(valid(self.io,self.p))
 def test_unpublished_report_cannot_be_approved(self):self.assertFalse(valid(self.io,dict(self.p,report_generation='not-published')))
 def test_legacy_plan_keeps_its_policy(self):self.assertFalse(valid(self.io,dict(self.p,validity_mode='legacy')))
if __name__=='__main__':unittest.main()

