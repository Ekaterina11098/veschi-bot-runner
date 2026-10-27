import copy,unittest
from china_advertising_midday import post_change_pending,revise_midday_bundle
class FullDayGuard(unittest.TestCase):
 def test_launch_without_membership_diff(self):
  c={'timestamps':{'started':'2026-10-26T21:22:51+03:00'}}
  self.assertTrue(post_change_pending([],1,2,'2026-10-27',c))
  self.assertFalse(post_change_pending([],1,2,'2026-10-28',c))
 def test_addition_in_other_campaign(self):
  event=dict(nm=2,cid=9,kind='added',at='2026-10-27T11:54:00Z')
  self.assertTrue(post_change_pending([event],1,2,'2026-10-28'))
  self.assertFalse(post_change_pending([event],1,2,'2026-10-29'))
 def test_msk_date_and_unchanged_other_sku(self):
  event=dict(nm=2,cid=9,kind='bid',at='2026-10-26T22:01:00Z')
  self.assertTrue(post_change_pending([event],1,2,'2026-10-28'))
  self.assertFalse(post_change_pending([event],1,3,'2026-10-28'))
 def test_naive_launch_fails_closed(self):
  with self.assertRaises(ValueError):post_change_pending([],1,2,'2026-10-27',{'timestamps':{'started':'2026-10-26T21:00:00'}})
 def test_correction_preserves_metrics_and_valid_action(self):
  action=lambda nm:dict(campaign_id=1,nm_id=nm,article=str(nm),kind='ad_exclude_sku')
  b=dict(day='2026-10-27',observed_at='2026-10-27T12:00:00Z',campaigns=[dict(id=1,today={'spend':12},attention=[dict(action=action(2)),dict(action=action(3))])])
  before=dict(id=9,nm_settings=[])
  after=dict(id=9,nm_settings=[dict(nm_id=2,bids_kopecks={'search':28})])
  rec=[dict(payload=dict(status='verified',verified_at='2026-10-27T11:54:00Z',before=before,after=after))]
  src=dict(batches={'0':dict(campaigns={'adverts':[dict(id=1)]})})
  result=revise_midday_bundle(b,src,rec)
  self.assertEqual([3],[x['action']['nm_id'] for x in result['campaigns'][0]['attention']])
  self.assertEqual(b['campaigns'][0]['today'],result['campaigns'][0]['today'])
  self.assertEqual(2,len(b['campaigns'][0]['attention']))
if __name__=='__main__':unittest.main()
