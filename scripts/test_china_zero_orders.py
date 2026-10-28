import unittest,copy
from datetime import datetime,timezone
from china_zero_orders import compute,period,recognizes,reconcile_created
class Zero(unittest.TestCase):
 def fixture(self):
  row=lambda n,c:dict(nm_id=n,article='SKU'+str(n),selected=dict(scope='all_sources',period_from='2026-10-14',period_to='2026-10-27',orders=c))
  return [(1,'SKU1'),(2,'SKU2'),(3,'SKU3')],dict(cabinet='token_3',currency='CNY',complete=True,period_from='2026-10-14',period_to='2026-10-27',rows=[row(1,0),row(2,4)])
 def check(self,cat,s):return compute(cat,s,'2026-10-14','2026-10-27')
 def test_all_orders_not_ad(self):
  cat,s=self.fixture();s['rows'][1]['advertising_orders']=0;r=self.check(cat,s);self.assertEqual(r['zero_count'],1);self.assertEqual(r['total_orders'],4);self.assertEqual(r['unknown_count'],1)
 def test_missing_counter_not_zero(self):
  cat,s=self.fixture();del s['rows'][0]['selected']['orders'];r=self.check(cat,s);self.assertEqual(r['zero_count'],0);self.assertEqual(r['unknown_count'],2)
 def test_partial_period_not_zero(self):
  cat,s=self.fixture();s['rows'][0]['selected']['period_from']='2026-10-21';self.assertEqual(self.check(cat,s)['zero_count'],0)
 def test_ad_only_not_all(self):
  cat,s=self.fixture();s['rows'][0]['selected']['scope']='advertising';self.assertEqual(self.check(cat,s)['zero_count'],0)
 def test_pagination_not_complete(self):
  cat,s=self.fixture();s['complete']=False;self.assertEqual(self.check(cat,s)['unknown_count'],3)
 def test_duplicate_not_zero(self):
  cat,s=self.fixture();s['rows'].append(copy.deepcopy(s['rows'][0]));self.assertEqual(self.check(cat,s)['zero_count'],0)
 def test_orders_not_buyouts(self):
  cat,s=self.fixture();s['rows'][1]['selected'].update(buyouts=0,cancellations=4);self.assertEqual(self.check(cat,s)['positive_count'],1)
 def test_completed_14_days(self):self.assertEqual(period('Нет заказов за последние 14 дней',datetime(2026,10,28,5,tzinfo=timezone.utc)),('2026-10-14','2026-10-27'))
 def test_explicit_dates_stay_fixed(self):self.assertEqual(period('Без заказов за 14–27 октября',datetime(2026,10,29,5,tzinfo=timezone.utc)),('2026-10-14','2026-10-27'))
 def test_created_order_conflict_not_zero(self):
  cat,s=self.fixture();r=self.check(cat,s);reconcile_created(r,dict(complete=True,cabinet='token_3',period_from='2026-10-14',period_to='2026-10-27',counts={'1':1},source_key='created',observed_at='now',total_orders=1,pages=1));self.assertEqual(r['zero_count'],0);self.assertEqual(r['unknown_count'],2)
 def test_created_orders_incomplete_rejected(self):
  cat,s=self.fixture()
  with self.assertRaises(ValueError):reconcile_created(self.check(cat,s),dict(complete=False))
 def test_correct_intent(self):self.assertTrue(recognizes('Дай списком товары которые не имеют заказов последние 14 дней'));self.assertFalse(recognizes('Дай список для повышения ставок'))
if __name__=='__main__':unittest.main()

