import copy,json,unittest
from unittest.mock import patch
from pathlib import Path
from china_advertising_full_growth import proposed_actions,addition_actions
class FullCabinetGrowthTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  path=Path(__file__).with_name('full-growth-fixture.json')
  if not path.exists():raise unittest.SkipTest('Private recorded fixture is exercised by the read-only cloud verifier')
  cls.fixture=json.loads(path.read_text(encoding='utf-8'))
 def source(self):
  x=copy.deepcopy(self.fixture)
  return dict(period_to=x['period_to'],executions=[],batches=x['batches'],full_growth_inputs=x['v']),x['changes']
 def evaluate(self,s,changes):
  with patch('china_advertising_v2.history',return_value=changes):return proposed_actions(s)
 def test_full_recorded_scope_and_eight_proposals(self):
  s,ch=self.source();a,u=self.evaluate(s,ch)
  self.assertEqual(len(s['full_growth_inputs']['screened_nm_ids']),312)
  self.assertEqual(len(a),8)
  self.assertFalse({x['nm_id']for x in a}&{1473245494,1473245510,1473244000})
  self.assertEqual(len({x['nm_id']for x in a}),len(a))
 def test_verified_changes_exclude_changed_day(self):
  s,ch=self.source();a,_=self.evaluate(s,ch)
  ch.extend(dict(nm=x['nm_id'],cid=x['campaign_id'],kind='bid',at='2026-11-03T15:00:00+00:00')for x in a)
  later,_=self.evaluate(s,ch)
  self.assertFalse({x['nm_id']for x in later}&{x['nm_id']for x in a})
 def test_unknown_published_stock_never_becomes_ready(self):
  s,ch=self.source()
  for e in s['full_growth_inputs']['economics']['rows'].values():e['published_stock']=None
  a,_=self.evaluate(s,ch);self.assertEqual(a,[])
 def test_three_day_reserve_required_without_auto_funding(self):
  s,ch=self.source()
  for row in s['full_growth_inputs']['budgets']['adverts']:row['total']=0
  a,u=self.evaluate(s,ch);self.assertEqual(a,[]);self.assertTrue(u)
 def test_exact_quote_is_required(self):
  s,ch=self.source();s['full_growth_inputs']['minimums']={}
  a,_=self.evaluate(s,ch);self.assertEqual(a,[])
 def test_nonpositive_own_economics_not_rescued_by_low_drr(self):
  s,ch=self.source()
  for e in s['full_growth_inputs']['economics']['rows'].values():e['expected_margin_before_ads_cny']=-1
  a,_=self.evaluate(s,ch);self.assertEqual(a,[])
 def test_empty_addition_scan_does_not_invent_proposals(self):
  s,_=self.source();self.assertEqual(addition_actions(s,[]),[])
if __name__=='__main__':unittest.main()
