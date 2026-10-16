import copy
import unittest
from datetime import date
from china_order_coverage import validate_orders

class CoverageTests(unittest.TestCase):
    def receipt(self, rows):
        return dict(scope_verified=True,status='received',observed_at='2026-10-16T10:00:00+00:00',
                    arguments=dict(type='products',value='42',date_from='2026-10-12',date_to='2026-10-15',start_row=0,end_row=300),
                    data=dict(data=rows,total=len(rows),filterModel=dict(product_id=dict(type='equals',filter=42),
                    order_dt=dict(type='inRange',dateFrom='2026-10-12',dateTo='2026-10-15'))))
    def check(self, obs):
        return validate_orders(obs,'100','42',date(2026,10,12),date(2026,10,15))
    def row(self, identity, day, cancel=0):
        return dict(nm_id=100,product_id=42,order_dt=day+' 12:30:00',gnumber=identity,is_canceled_order=cancel)
    def test_explicit_empty_receipt_confirms_zero(self):
        self.assertEqual(self.check(self.receipt([]))['orders_each_day'],[0,0,0,0])
    def test_unknown_or_wrong_filters_never_confirm_zero(self):
        for field,value in [('filterModel',{}),('total',1)]:
            obs=self.receipt([]);obs['data'][field]=value
            with self.assertRaises(ValueError):self.check(obs)
    def test_cancellations_and_dates_separate(self):
        rows=[self.row('a','2026-10-12'),self.row('b','2026-10-12',1),self.row('c','2026-10-15')]
        result=self.check(self.receipt(rows))
        self.assertEqual(result['orders_each_day'],[1,0,0,1])
        self.assertEqual(result['all_orders_each_day'],[2,0,0,1])
        self.assertEqual(result['cancelled_orders'],1)
        self.assertFalse(result['financial_data_complete'])
    def test_duplicates_or_other_sku_rejected(self):
        a=self.row('a','2026-10-12')
        for rows in ([a,copy.deepcopy(a)],[dict(a,nm_id=999)],[dict(a,order_dt='2026-10-16 12:00:00')]):
            with self.assertRaises(ValueError):self.check(self.receipt(rows))
    def test_previous_period_rejected(self):
        obs=self.receipt([]);obs['arguments']['date_to']='2026-10-14'
        with self.assertRaises(ValueError):self.check(obs)

if __name__=='__main__':unittest.main()
