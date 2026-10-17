"""Regression checks for WB-priority period outcomes, no network."""
import unittest
from china_daily_expected_control import order_outcomes,comparison_windows
from datetime import date

class CohortTests(unittest.TestCase):
 def setUp(self):
  self.wb=[dict(nmId=1,supplierArticle='a',srid=str(i),date='2026-10-05T'+hour+':00:00',barcode='x',isCancel=cancel) for i,hour,cancel in [(1,'10',True),(2,'11',False),(3,'12',False)]]
  self.rows=[dict(nm_id=1,api_id=10026946,sa_name='a',order_dt='2026-10-05 '+hour+':00:00',barcode='x',billed_times=paid,refunded_times=0,backlogistic_times=0,sale_date='2026-10-15' if paid else None) for hour,paid in [('10',0),('11',1)]]
 def result(self,wb=None,rows=None):
  return order_outcomes(self.wb if wb is None else wb,self.rows if rows is None else rows,1,'a','2026-10-05','2026-10-08')
 def test_baseline_stays_four_days_while_after_period_grows(self):
  for day in range(17,21):
   before,after=comparison_windows(date(2026,10,15),date(2026,10,day))
   self.assertEqual(before,(date(2026,10,11),date(2026,10,14)))
   self.assertEqual((after[1]-after[0]).days+1,day-16)
  self.assertIsNone(comparison_windows(date(2026,10,15),date(2026,10,16)))
 def test_wb_cancellation_overrides_pending_and_missing_is_unknown(self):
  self.assertEqual(self.result(),dict(orders=3,paid=1,cancelled=1,returned=0,pending=0,unknown=1,completed=2))
 def test_srid_duplicate_does_not_double_orders(self):
  self.assertEqual(self.result(self.wb+[self.wb[0]])['orders'],3)
 def test_late_buyout_and_return_belong_to_order_period(self):
  self.assertEqual(self.result()['paid'],1)
  self.rows[1]['refunded_times']=1
  self.assertEqual(self.result()['returned'],1)
  self.assertEqual(self.result()['paid'],0)
  self.assertEqual(order_outcomes(self.wb,self.rows,1,'a','2026-10-15','2026-10-16')['orders'],0)
 def test_two_real_orders_with_same_time_are_preserved(self):
  self.wb[2]['date']=self.wb[1]['date']
  self.rows.append(dict(self.rows[1]))
  r=self.result()
  self.assertEqual((r['orders'],r['paid'],r['completed']),(3,2,3))
if __name__=='__main__':unittest.main()
