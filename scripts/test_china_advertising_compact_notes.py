import unittest
from china_advertising_png import campaign_notes
from china_advertising_normalize import normalize
from test_china_advertising_normalize import fixture

class CompactNotes(unittest.TestCase):
 def notes(self,c):return campaign_notes(c,lambda v:str(v)+' ¥',lambda v:str(v)+'%')
 def test_spend_without_orders_not_hidden_by_sold_sku(self):
  p=fixture();products=p['observations'][5]['data']
  products['data']=[dict(nm_id=1,ac_spending_sum=27,ac_orders=3,ac_orders_sum=4908),dict(nm_id=2,ac_spending_sum=273,ac_orders=0,ac_orders_sum=0),dict(nm_id=3,ac_spending_sum=0,ac_orders=0,ac_orders_sum=0)]
  products['returned']=3;products['totals']['ac_spending_sum']=300
  p['observations'][1]['data']['data'][0].update(ac_spending_sum=300,ac_orders_sum=4908)
  c=normalize(p,'2026-10-20',{})['campaigns'][0];text=' '.join(self.notes(c))
  self.assertGreater(c['drr'],5);self.assertEqual(len(c['no_orders']),1)
  self.assertIn('У товаров с заказами ДРР до 5%',text)
  self.assertIn('Без заказов: 1 товар · 273 ¥',text)
 def test_missing_orders_block_unknown_not_zero(self):
  p=fixture();del p['observations'][5]['data']['data'][0]['ac_orders']
  with self.assertRaises(ValueError):normalize(p,'2026-10-20',{})
 def test_no_activity_not_bad_product(self):
  c=dict(is_new=False,spend=0,above5=[],no_orders=[])
  self.assertEqual(self.notes(c),['За день не откручивалась'])
 def test_only_spending_no_orders(self):
  c=dict(is_new=False,spend=4,above5=[],no_orders=[dict(spend=4)],sku_with_orders_count=0)
  self.assertEqual(self.notes(c),['Прямых заказов нет','Без заказов: 1 товар · 4 ¥'])
 def test_new_outside_period(self):
  c=dict(is_new=True,created='2026-10-20',above5=[])
  self.assertIn('вне отчётного периода',self.notes(c)[0])
if __name__=='__main__':unittest.main()
