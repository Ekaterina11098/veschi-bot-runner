import copy,unittest
from unittest.mock import patch
from china_advertising_midday import prepare_midday,post_change_pending,current_report_context
from china_budget_context import KEY
class IO:
 def __init__(self):
  before=dict(id=1,nm_settings=[dict(nm_id=2,bids_kopecks=dict(search=28))])
  after=dict(id=1,nm_settings=[dict(nm_id=2,bids_kopecks=dict(search=34))])
  self.rows={'china_agent:verified_campaign_state:v1':{'1':'receipt'},'receipt':dict(status='verified',verified_at='2026-10-27T08:44:34Z',before=before,after=after),
   KEY:dict(status='active',mode='manual_only',observed_at='2020-01-01T00:00:00Z',valid_until='2099-01-01T00:00:00Z',campaigns={'1':dict(status='manual_funded',remaining_manual_cny=0)})}
 def get(self,k):return copy.deepcopy(self.rows.get(k))
def event(day='2026-10-26',kind='bid',cid=1):
 return dict(cid=cid,nm=2,kind=kind,at=day+'T08:00:00Z')
class MiddayStateRegression(unittest.TestCase):
 def test_first_following_day_must_finish(self):
  self.assertTrue(post_change_pending([event()],1,2,'2026-10-27'))
  self.assertFalse(post_change_pending([event()],1,2,'2026-10-28'))
 def test_today_bid_in_another_campaign_is_protected(self):
  self.assertTrue(post_change_pending([event('2026-10-27',cid=5)],1,2,'2026-10-27'))
 def test_price_change_without_campaign_is_protected(self):
  self.assertTrue(post_change_pending([event(kind='price',cid=None)],1,2,'2026-10-27'))
 def test_registry_loaded_even_when_source_history_empty(self):
  rows,ctx=current_report_context(IO(),dict(executions=[]),'2026-10-27')
  self.assertEqual('receipt',rows[0]['cache_key'])
  self.assertEqual(0,ctx['manual_funding']['campaigns']['1']['remaining_manual_cny'])
 def test_invalid_registry_cannot_silently_drop_changes(self):
  io=IO();io.rows['receipt']['status']='uncertain'
  with self.assertRaises(ValueError):current_report_context(io,dict(executions=[]),'2026-10-27')
 def test_registry_blocks_duplicate_recommendation_without_wb_call(self):
  metrics=dict(sum=20,sum_price=0,orders=0,views=200,clicks=50)
  n=dict(nmId=2,**metrics)
  camp=dict(id=1,status=9,settings=dict(name='Test',placements=dict(search=True)),nm_settings=[dict(nm_id=2,bids_kopecks=dict(search=34))])
  source=dict(observed_at='2026-10-27T12:00:00Z',catalogue=dict(rows=[dict(nmID=2,vendorCode='Bag',price=100)]),executions=[],batches={'0':dict(campaigns=dict(adverts=[camp]),stats=[dict(advertId=1,days=[dict(date='2026-10-27',apps=[dict(nms=[n])],**metrics)])])})
  with patch('china_advertising_midday.collect',return_value=source),patch('china_advertising_midday.http',side_effect=AssertionError('No WB call for protected SKU')):
   b=prepare_midday(IO(),'2026-10-27')
  self.assertEqual([],b['campaigns'][0]['attention'])
  self.assertEqual({'1':'receipt'},b['review_context']['verified_registry'])
if __name__=='__main__':unittest.main()
