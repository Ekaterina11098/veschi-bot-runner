import unittest
from advertising_current_promotion import guard
class PromotionEpochTests(unittest.TestCase):
 def config(self):return dict(id=17814,payload=dict(adverts=[dict(id=40223879,timestamps=dict(started='2026-10-16T10:59:17+03:00'))]))
 def report(self,start):return dict(period_from=start,period_to='2026-10-23',campaigns=[dict(wb_campaign_id=40223879,totals=dict(ac_spending_sum=10),products=[dict(nm_id=1,advertising=dict(ac_orders=5),shop_economics=dict(net_profit=20))]),dict(wb_campaign_id=1,totals=dict(ac_spending_sum=5))])
 def test_prior_and_partial_days_not_current(self):
  for start in ['2026-10-09','2026-10-16']:
   source=self.report(start);r=guard(source,self.config())
   self.assertEqual(r['campaigns'][0]['totals'],{});self.assertEqual(r['campaigns'][0]['historical_advertising_totals']['ac_spending_sum'],10)
   self.assertEqual(r['campaigns'][0]['products'][0]['shop_economics']['net_profit'],20)
   self.assertEqual(source['campaigns'][0]['totals']['ac_spending_sum'],10)
   self.assertEqual(r['campaigns'][1]['totals']['ac_spending_sum'],5)
 def test_full_postlaunch_period_usable(self):
  r=guard(self.report('2026-10-17'),self.config());self.assertTrue(r['campaigns'][0]['current_promotion']['current_promotion_metrics_verified'])
if __name__=='__main__':unittest.main()
