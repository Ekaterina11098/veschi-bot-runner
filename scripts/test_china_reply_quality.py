import unittest
from datetime import datetime,timezone
from china_reply_quality import normalize_answer,current_memberships
class Worker:
 now=datetime(2026,10,26,6,10,tzinfo=timezone.utc)
 def catalog(self):return [('1','141-test'),('2','023-test')]
 def get(self,key):
  return dict(complete=True,observed_at='2026-10-26T06:10:00Z',campaigns=[
   dict(id=12,status=9,settings=dict(placements=dict(search=False)),nm_settings=[dict(nm_id=2,bids_kopecks=dict(recommendations=28))]),
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
if __name__=='__main__':unittest.main()
