import unittest
from china_midday_completed_review import merge_completed
from china_advertising_midday import only_completed_day_actions,recommendations
class CompletedMidday(unittest.TestCase):
 def review(self):
  return dict(days=['2026-10-31'],campaigns=[dict(id=1,focus=[dict(nm=2,article='Bag',period=dict(spend=10,clicks=50,orders=2,amount=100),decision='Снизить 0,34 → 0,28',action=dict(kind='ad_set_bid',nm_id=2))])])
 def test_completed_recommendation_survives_filter_with_real_order_count(self):
  b=dict(day='2026-11-01',campaigns=[dict(id=1,attention=[])])
  out=only_completed_day_actions(merge_completed(b,self.review(),'private_closed_source'))
  self.assertEqual(1,len(out['campaigns'][0]['attention']))
  text=recommendations(out['campaigns'][0])[0];self.assertIn('2 заказов',text);self.assertIn('полные 2026-10-31',text);self.assertNotIn('0 рекламных заказов',text)
 def test_incomplete_day_cannot_become_action_evidence(self):
  r=self.review();r['days']=['2026-11-01']
  with self.assertRaises(ValueError):merge_completed(dict(day='2026-11-01',campaigns=[dict(id=1)]),r,'source')
 def test_pending_history_remains_private_and_not_recommended(self):
  r=self.review();r['campaigns'][0]['focus'][0].update(pending_first_day=True,done='Ставка снижена · 01.11')
  out=merge_completed(dict(day='2026-11-01',campaigns=[dict(id=1)]),r,'source')
  self.assertEqual([],out['campaigns'][0]['attention']);self.assertEqual(['Нет новых действий.'],recommendations(out['campaigns'][0]));self.assertTrue(out['campaigns'][0]['completed_actions'])
if __name__=='__main__':unittest.main()

