import unittest
from datetime import datetime,timezone
from advertising_budget_evidence import budget_analysis
class BudgetEvidenceTests(unittest.TestCase):
 def report(self,payload):return dict(budgets=[dict(id=17735,payload=payload)],campaigns=[dict(wb_campaign_id=1,active_catalog_verified=True),dict(wb_campaign_id=2,active_catalog_verified=True)])
 def test_old_is_visible_not_current(self):
  r=budget_analysis(self.report(dict(items=[dict(campaign_id=1,total=123,available=True,observed_at='2026-10-16T01:00:00+00:00')])),datetime(2026,10,16,16,tzinfo=timezone.utc))
  self.assertEqual(r[0]['balance'],123);self.assertFalse(r[0]['balance_is_current']);self.assertEqual(r[0]['balance_status'],'historical');self.assertIsNone(r[1]['balance']);self.assertIsNone(r[0]['forecast_hours'])
 def test_list_payload_and_real_zero(self):
  r=budget_analysis(self.report([dict(items=[dict(campaign_id=1,total=0,available=True,observed_at='2026-10-16T15:00:00+00:00')])]),datetime(2026,10,16,16,tzinfo=timezone.utc))
  self.assertEqual(r[0]['balance'],0);self.assertTrue(r[0]['balance_is_current'])
 def test_missing_or_invalid_not_zero(self):
  for total in [None,float('nan'),-1]:
   r=budget_analysis(self.report(dict(items=[dict(campaign_id=1,total=total,available=True,observed_at='2026-10-16T01:00:00+00:00')])),datetime(2026,10,16,16,tzinfo=timezone.utc))
   self.assertIsNone(r[0]['balance'])
if __name__=='__main__':unittest.main()
