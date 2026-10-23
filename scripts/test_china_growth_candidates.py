import copy,unittest
from datetime import date
from china_growth_candidates import score,within_full_days

def fixture():
 row=dict(nm_id=10,sa_name='test-bag',subject_id=50,finished_orders=10,is_payed=8,open_card_count=100,funnel_orders_count=10,price_after_spp=100,price_after_discount=100)
 source=dict(products=[row],prices=[dict(nmID=10,sizes=[dict(discountedPrice=100)])],stock=[dict(article='test-bag',stock=100,reserve=0,price=10000)],orders=[dict(nmId=10)],policy=dict(fx_rub_cny=12,logistics_by_nm={'10':dict(delivery_cny=1)}),experience=dict(experiences=[]))
 campaign=dict(currency='CNY',bid_type='manual',settings=dict(payment_type='cpc',placements=dict(search=False,recommendations=True)),nm_settings=[dict(nm_id=10,bids_kopecks=dict(recommendations=40))])
 daily={'1:10':{str(date(2026,10,d)):dict(spend=4,amount=300,orders=3,clicks=10,views=100) for d in [20,21,22]}}
 return source,{1:campaign},daily

class CandidateMemoryTests(unittest.TestCase):
 def run_score(self,s,c,d,recent=set(),protected=set()):
  return score(s,c,d,{(1,10):28},dict(cpcStep=1,cpcMaxBid=1000),protected,recent,{('orders',50):(2,28)},date(2026,10,23))
 def test_raise_allowed_with_evidence_but_not_after_recent_change(self):
  s,c,d=fixture();rows,_=self.run_score(s,c,d)
  self.assertEqual(rows[0]['target_minor'],42);self.assertTrue(rows[0]['memory']['requires_confirmation'])
  self.assertFalse(self.run_score(s,c,d,{10})[0])
 def test_negative_experience_changes_selection_for_raise_and_add(self):
  s,c,d=fixture();s['experience']['experiences']=[dict(event_id='bad',business_outcome='negative',action=dict(nm_ids=[10]),context=dict(seller_price=100))]
  for campaigns in [c,{}]:
   rows,blocked=self.run_score(s,campaigns,d)
   self.assertFalse(rows);self.assertEqual(blocked[0]['memory']['event_ids'],['bad'])
 def test_changed_conditions_allow_reviewed_new_test_without_guarantee(self):
  s,c,d=fixture();s['experience']['experiences']=[dict(event_id='bad',business_outcome='negative',action=dict(nm_ids=[10]),context=dict(seller_price=90))]
  rows,_=self.run_score(s,c,d);self.assertTrue(rows[0]['memory']['risks']);self.assertTrue(rows[0]['memory']['requires_confirmation'])
 def test_additions_use_history_and_respect_previous_exclusion(self):
  s,c,d=fixture();rows,_=self.run_score(s,{},d)
  self.assertEqual(rows[0]['kind'],'ad_add_sku');self.assertFalse(self.run_score(s,{},d,protected={10})[0])
 def test_three_full_days_after_actual_change(self):
  self.assertTrue(within_full_days('2026-10-23T16:00:00Z',date(2026,10,26)))
  self.assertFalse(within_full_days('2026-10-23T16:00:00Z',date(2026,10,27)))

if __name__=='__main__':unittest.main()
