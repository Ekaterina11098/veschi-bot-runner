import ast,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta

tree=ast.parse(Path(__file__).with_name('advertising_source_owner.py').read_text(encoding='utf-8'))
names={'campaign_day_gaps','finance_refresh_reason','daily_refresh_dates','financial_response_state'}
ns={};exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'actual-source','exec'),ns)
NOW=datetime(2026,10,16,13,tzinfo=timezone.utc)
class Revisions(unittest.TestCase):
 def reason(self,age,day='2026-10-15',explicit=False):
  return ns['finance_refresh_reason'](day,[dict(observation_status='received',observed_at=(NOW-timedelta(hours=age)).isoformat())],NOW,explicit)
 def test_fresh_complete_is_cached_not_final(self):self.assertIsNone(self.reason(1))
 def test_recent_complete_refreshed_after24h(self):self.assertEqual(self.reason(24),'late_accrual_revision')
 def test_old_not_recollected(self):self.assertIsNone(self.reason(100,'2026-09-01'))
 def test_specific_old_incident_refresh(self):self.assertEqual(self.reason(100,'2026-09-01',True),'late_accrual_revision')
 def test_future_not_requested(self):self.assertIsNone(self.reason(1,'2026-10-17'))
 def test_unknown_freshness_not_zero(self):self.assertEqual(ns['finance_refresh_reason']('2026-10-15',[dict(observation_status='received')],NOW),'freshness_unknown')
 def test_no_history_missing(self):self.assertEqual(ns['finance_refresh_reason']('2026-10-15',[],NOW),'missing')
 def test_response_not_settlement(self):
  s=ns['financial_response_state'](dict(status='received',scope_verified=True,data=dict(data=dict(need_update=0,total=1,data=[dict(advertisement=0)]))))
  self.assertTrue(s['response_complete']);self.assertFalse(s['accruals_final']);self.assertFalse(s['zero_advertisement_is_final_absence']);self.assertFalse(s['campaign_spend_additive'])
 def test_truncated_response(self):self.assertFalse(ns['financial_response_state'](dict(status='received',scope_verified=True,data=dict(data=dict(need_update=0,total=2,data=[]))))['response_complete'])
 def test_daily_refresh_is_scoped(self):
  s=[dict(collected_at=NOW.isoformat(),payload=[dict(campaign_id=1,report='days',scope_nm_id=None,spending_reconciled=True,rows=[dict(date='2026-10-15',ac_spending_sum=0)])])]
  self.assertEqual(ns['daily_refresh_dates'](s,1,'2026-10-09','2026-10-15',NOW),{'2026-10-13','2026-10-14'})
 def test_refresh_preserves_other_days(self):
  s=[dict(payload=[dict(campaign_id=1,report='days',spending_reconciled=True,rows=[dict(date=f'2026-10-{n}',ac_spending_sum=1) for n in range(12,16)])])]
  self.assertEqual(ns['campaign_day_gaps'](s,1,'2026-10-12','2026-10-15',{'2026-10-15'}),[('2026-10-15','2026-10-15')])
 def test_source_compiles(self):compile(tree,'source','exec')
if __name__=='__main__':unittest.main()
