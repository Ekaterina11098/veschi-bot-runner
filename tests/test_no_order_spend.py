import unittest
from advertising_budget_evidence import no_order_spend_summary

class NoOrderSpend(unittest.TestCase):
 def summarize(self,rows,basis='direct_only',total=100):
  return no_order_spend_summary(dict(rows=rows,sku_order_basis=basis,totals={'ac_spending_sum':total}))
 def test_positive_spend_only(self):
  rows=[dict(nm_id=1,ac_spending_sum=30,ac_orders=0),dict(nm_id=2,ac_spending_sum=0,ac_orders=0),dict(nm_id=3,ac_spending_sum=70,ac_orders=1)]
  self.assertEqual(self.summarize(rows),dict(no_order_count=1,no_order_spend=30))
 def test_group_same_sku(self):
  rows=[dict(nm_id=1,ac_spending_sum=30,ac_orders=0),dict(nm_id=1,ac_spending_sum=0,ac_orders=1)]
  self.assertEqual(self.summarize(rows),dict(no_order_count=0,no_order_spend=0))
 def test_missing_orders_not_zero(self):
  self.assertIsNone(self.summarize([dict(nm_id=1,ac_spending_sum=30)])['no_order_count'])
 def test_aggregate_not_sku(self):
  self.assertIsNone(self.summarize([],basis='aggregate_only')['no_order_count'])
 def test_empty_positive_spend_unknown(self):
  self.assertIsNone(self.summarize([])['no_order_count'])
 def test_verified_no_spend(self):
  self.assertEqual(self.summarize([],total=0),dict(no_order_count=0,no_order_spend=0))

if __name__=='__main__':unittest.main()

