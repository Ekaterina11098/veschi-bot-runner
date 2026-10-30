import copy,unittest
from china_advertising_midday import only_completed_day_actions
class MiddayCompletedEvidence(unittest.TestCase):
 def test_incomplete_day_losses_do_not_become_ready_actions(self):
  b=dict(day='2026-10-30',campaigns=[dict(id=1,today=dict(spend=500,orders=0),attention=[dict(action=dict(kind='ad_exclude_sku'),spend=500,clicks=1000)])])
  old=copy.deepcopy(b);r=only_completed_day_actions(b)
  self.assertEqual(r['campaigns'][0]['attention'],[]);self.assertEqual(r['campaigns'][0]['today'],b['campaigns'][0]['today']);self.assertEqual(b,old)
 def test_closed_evidence_needs_postclick_and_actual_closed_date(self):
  base=dict(action=dict(kind='ad_set_bid'),closed_day_evidence=dict(verified=True,source_ref='canonical_closed_source',postclick_reviewed=True,period_to='2026-10-29'))
  b=dict(day='2026-10-30',campaigns=[dict(attention=[base])])
  self.assertEqual(len(only_completed_day_actions(b)['campaigns'][0]['attention']),1)
  for field,value in [('period_to','2026-10-30'),('period_to','invalid'),('postclick_reviewed',False),('verified',False),('source_ref','')]:
   c=copy.deepcopy(b);c['campaigns'][0]['attention'][0]['closed_day_evidence'][field]=value
   self.assertEqual(only_completed_day_actions(c)['campaigns'][0]['attention'],[])
