import unittest
from datetime import datetime,timezone
from china_reply_quality import normalize_answer,current_memberships
class Worker:
 now=datetime(2026,10,26,6,10,tzinfo=timezone.utc)
 def catalog(self):return [('1','141-test'),('2','023-test')]
 def get(self,key):
  return dict(complete=True,observed_at='2026-10-26T06:10:00Z',campaigns=[
   dict(id=12,status=9,settings=dict(placements=dict(search=False,recommendations=True)),nm_settings=[dict(nm_id=2,bids_kopecks=dict(recommendations=28))]),
   dict(id=13,status=9,settings=dict(placements=dict(search=True)),nm_settings=[dict(nm_id=1,bids_kopecks=dict(search=28))]),
   dict(id=14,status=11,settings=dict(placements=dict(search=True)),nm_settings=[dict(nm_id=1,bids_kopecks=dict(search=28))])])
class QualityTests(unittest.TestCase):
 def test_literal_paragraphs_and_markdown_become_plain_text(self):
  self.assertEqual(normalize_answer('**1907,12 ¥**'+r'\n\n'+'За вчера'),'1907,12 ¥\n\nЗа вчера')
 def test_windows_path_not_unescaped(self):
  self.assertEqual(normalize_answer(r'C:\new-chat'),r'C:\new-chat')
 def test_png_markers_not_changed(self):
  self.assertEqual(normalize_answer('[[report:abc]]'),'[[report:abc]]')
 def test_excluded_in_one_campaign_can_remain_elsewhere(self):
  m=current_memberships(Worker());self.assertEqual(m['active_memberships']['141-test'],[dict(rc=13,zone='поиск',bid_cny=.28)])
  self.assertEqual(m['active_memberships']['023-test'][0]['rc'],12);self.assertEqual(m['wb_reads'],0)
 def test_missing_current_data_not_called_excluded(self):
  w=Worker();w.get=lambda k:None;self.assertFalse(current_memberships(w)['available'])

class OverlayTests(unittest.TestCase):
 def worker(self):
  w=Worker();base=w.get('base');registry={};receipts={}
  w.get=lambda k:base if k.startswith('china_agent:advertising_intraday:') else registry if k=='china_agent:verified_campaign_state:v1' else receipts.get(k)
  return w,base,registry,receipts
 def verified(self,cid=13,ids=()):
  return dict(status='verified',verified_at='2026-10-26T06:11:00Z',after=dict(id=cid,status=9,settings=dict(placements=dict(search=True)),nm_settings=[dict(nm_id=i,bids_kopecks=dict(search=35)) for i in ids]))
 def test_later_verified_removal_replaces_stale_membership(self):
  w,b,r,e=self.worker();w.now=datetime(2026,10,26,6,12,tzinfo=timezone.utc);r['13']='receipt';e['receipt']=self.verified()
  m=current_memberships(w);self.assertNotIn('141-test',m['active_memberships']);self.assertTrue(m['complete']);self.assertEqual(m['wb_reads'],0)
 def test_later_verified_bid_overrides_older_cached_bid(self):
  w,b,r,e=self.worker();w.now=datetime(2026,10,26,6,12,tzinfo=timezone.utc);r['13']='receipt';e['receipt']=self.verified(ids=[1])
  self.assertEqual(current_memberships(w)['active_memberships']['141-test'][0]['bid_cny'],.35)
 def test_older_receipt_does_not_rollback_newer_full_snapshot(self):
  w,b,r,e=self.worker();r['13']='receipt';e['receipt']=self.verified();e['receipt']['verified_at']='2026-10-26T06:09:00Z'
  self.assertIn('141-test',current_memberships(w)['active_memberships'])
 def test_invalid_future_missing_or_unverified_child_keeps_scope_incomplete(self):
  for mode in ['missing','wrong_id','pending','future']:
   with self.subTest(mode=mode):
    w,b,r,e=self.worker();w.now=datetime(2026,10,26,6,12,tzinfo=timezone.utc);r['13']='receipt';e['receipt']=self.verified()
    if mode=='missing':e.clear()
    if mode=='wrong_id':e['receipt']['after']['id']=99
    if mode=='pending':e['receipt']['status']='pending'
    if mode=='future':e['receipt']['verified_at']='2999-10-26T08:00:00Z'
    self.assertFalse(current_memberships(w)['complete'])
 def test_receipt_completed_after_worker_start_is_still_current(self):
  w,b,r,e=self.worker();r['13']='receipt';e['receipt']=self.verified()
  self.assertNotIn('141-test',current_memberships(w)['active_memberships'])
 def test_missing_bid_is_unknown_not_zero(self):
  w,b,r,e=self.worker();b['campaigns'][1]['nm_settings'][0]['bids_kopecks']={}
  self.assertIsNone(current_memberships(w)['active_memberships']['141-test'][0]['bid_cny'])
 def test_both_placements_reported_separately(self):
  w,b,r,e=self.worker();c=b['campaigns'][1];c['settings']['placements']['recommendations']=True;c['nm_settings'][0]['bids_kopecks']['recommendations']=40
  rows=current_memberships(w)['active_memberships']['141-test'];self.assertEqual(len(rows),2);self.assertEqual({x['zone'] for x in rows},{'поиск','рекомендации'})
 def test_missing_placements_does_not_assume_recommendations(self):
  w,b,r,e=self.worker();b['campaigns'][1]['settings']['placements']={}
  m=current_memberships(w);self.assertFalse(m['complete']);self.assertNotIn('141-test',m['active_memberships'])
if __name__=='__main__':unittest.main()

