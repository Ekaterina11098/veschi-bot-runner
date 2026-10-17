import unittest
from china_order_cohort_math import cohort
class CohortTests(unittest.TestCase):
 def row(self,**kw):
  return dict(nm_id=1,api_id=10026946,sa_name='A',gnumber='x',order_dt='2026-10-14 12:00:00',is_canceled_order=0,billed_times=1,refunded_times=0,sale_date='2026-10-16',billedmoney=1000,refundedmoney=0,comission=100,forward_logistic_rub=50,backward_logistic_rub=0,**kw)
 def test_sale_belongs_to_original_order(self):
  r=self.row();self.assertEqual(cohort([r],1,'A','2026-10-14',200)['realized_contribution'],650);self.assertEqual(cohort([r],1,'A','2026-10-16',200)['realized_contribution'],0)
 def test_pending_forecast_is_not_realized(self):
  r=self.row();r.update(billed_times=0,sale_date=None,billedmoney=0,profit=999,order_for_pay=1500)
  result=cohort([r],1,'A','2026-10-14',200);self.assertEqual(result['realized_contribution'],0);self.assertEqual(result['pending'],1);self.assertFalse(result['finalized'])
 def test_duplicate_is_not_double_counted(self):
  r=self.row();self.assertEqual(cohort([r,r],1,'A','2026-10-14',200)['orders'],1)
 def test_return_reverses_cogs_in_original_order(self):
  r=self.row();r.update(refunded_times=1,refundedmoney=1000,refund_dt='2026-10-17',backward_logistic_rub=40)
  self.assertEqual(cohort([r],1,'A','2026-10-14',200)['realized_contribution'],-190)
if __name__=='__main__':unittest.main()
