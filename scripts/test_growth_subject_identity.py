import unittest,copy
from china_growth_placements import placement_candidates
class SubjectIdentity(unittest.TestCase):
 def fixture(self):
  cp=dict(id=20,status=9,currency='CNY',bid_type='manual',settings=dict(payment_type='cpc',placements=dict(search=True)),restrictions=dict(can_change_nms=True),nm_settings=[dict(nm_id=2,subject=dict(id=50))])
  own=dict(nm_id=1,is_payed=5,open_card_count=100,funnel_orders_count=5,subject_id=50)
  econ=dict(expected_margin_before_ads_cny=10,sample_size=10,stock_free=10,published_stock=10)
  return dict(period_to='2026-11-10',executions=[]),dict(campaigns=[cp],own=dict(rows=[own]),economics=dict(rows={'1':econ}),screened_nm_ids=[1],excluded_nm_ids=[])
 def test_exact_category_finds_absent_placement(self):
  s,v=self.fixture();a=placement_candidates(s,v)
  self.assertEqual([(r['nm_id'],r['campaign_id'],r['subject_id'])for r in a],[(1,20,50)])
 def test_missing_category_is_incomplete_not_zero_candidates(self):
  s,v=self.fixture();v['own']['rows'][0].pop('subject_id')
  with self.assertRaisesRegex(ValueError,'subject missing'):placement_candidates(s,v)
 def test_incompatible_category_is_not_added(self):
  s,v=self.fixture();v['own']['rows'][0]['subject_id']=136
  self.assertEqual(placement_candidates(s,v),[])
 def test_no_duplicate_occupied_placement(self):
  s,v=self.fixture();v['campaigns'][0]['nm_settings'].append(dict(nm_id=1,subject=dict(id=50)))
  self.assertEqual(placement_candidates(s,v),[])
 def test_owner_hold_is_preserved(self):
  s,v=self.fixture();v['excluded_nm_ids']=[1]
  self.assertEqual(placement_candidates(s,v),[])
if __name__=='__main__':unittest.main()
