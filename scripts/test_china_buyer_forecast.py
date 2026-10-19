import unittest,copy,sys,types
from datetime import date
import china_buyer_price_forecast as module
from china_buyer_price_forecast import build,forecast
DAY=date(2026,10,19)
def fixture():
 rows=[dict(nm_id=1473243906,sa_name='51-NoelBag-green',price_after_spp=1960,price_final=1960,price_after_discount=2362,price_spp=17)]
 marker=dict(id=18445,period_from='2026-10-18',period_to='2026-10-18',collected_at='2026-10-19T08:18:29+00:00')
 cat=dict(cabinet='token_3',observed_at='2026-10-19T11:14:29+03:00',rows=[dict(nmID=1473243906,vendorCode='51-NoelBag-green',currencyIsoCode4217='CNY',sizes=[dict(discountedPrice=180)])])
 return rows,marker,cat
class BuyerForecastTests(unittest.TestCase):
 def test_known_increase(self):
  basis=build(*fixture(),DAY)
  self.assertEqual(forecast(basis,1473243906,'51-NoelBag-green',180,198,DAY),2156)
  self.assertEqual(basis['snapshot_id'],18445)
 def test_decrease(self):
  rows,marker,cat=fixture();rows[0].update(price_after_spp=1160,price_final=1160,price_after_discount=1399);cat['rows'][0]['sizes'][0]['discountedPrice']=106.6
  self.assertEqual(forecast(build(rows,marker,cat,DAY),1473243906,'51-NoelBag-green',106.6,82,DAY),892)
 def test_old_snapshot_no_guess(self):
  rows,marker,cat=fixture();marker['collected_at']='2026-10-18T08:18:29+00:00'
  self.assertIsNone(forecast(build(rows,marker,cat,DAY),1473243906,'51-NoelBag-green',180,198,DAY))
 def test_changed_seller_price_no_guess(self):
  self.assertIsNone(forecast(build(*fixture(),DAY),1473243906,'51-NoelBag-green',181,198,DAY))
 def test_conflicting_buyer_prices(self):
  rows,marker,cat=fixture();rows[0]['price_final']=1961
  self.assertEqual(build(rows,marker,cat,DAY)['rows'],{})
 def test_wrong_spp_relationship(self):
  rows,marker,cat=fixture();rows[0]['price_spp']=50
  self.assertEqual(build(rows,marker,cat,DAY)['rows'],{})
 def test_ambiguous_size_no_guess(self):
  rows,marker,cat=fixture();cat['rows'][0]['sizes'].append(dict(discountedPrice=181))
  self.assertEqual(build(rows,marker,cat,DAY)['rows'],{})
 def test_wrong_cabinet_no_guess(self):
  rows,marker,cat=fixture();cat['cabinet']='token_1'
  self.assertEqual(build(rows,marker,cat,DAY)['status'],'unavailable')
 def test_duplicate_product_no_guess(self):
  rows,marker,cat=fixture();rows.append(copy.deepcopy(rows[0]))
  self.assertEqual(build(rows,marker,cat,DAY)['rows'],{})
 def test_brief_integration(self):
  # Dependency alias only, no source services or worker imports.
  if 'china_agent' not in sys.modules:
   sys.modules['china_agent']=types.ModuleType('china_agent')
  sys.modules['china_agent.buyer_price_forecast']=module
  from china_price_brief import render,article_entities
  basis=build(*fixture(),DAY)
  review=dict(report_date=str(DAY),status='complete_disclosed_forecast_model',model_version='wb_four_day_baseline_daily_means_v3',products=[])
  source='Первое повышение +10%: 1 кандидатов.\n• 51-NoelBag-green: заказы 3/2/2/3.\n  Предложение: 180 → 198 ¥ после скидки, с округлением.'
  text=render(source,'intraday',review,DAY,fixture()[2],basis)
  self.assertIn('Цена покупателя (прогноз): 2 156 ₽',text)
  self.assertEqual(article_entities(text)[0]['url'],'https://www.wildberries.ru/catalog/1473243906/detail.aspx')
  text=render(source,'intraday',review,DAY,fixture()[2],dict(report_date=str(DAY),status='unavailable'))
  self.assertIn('Цена покупателя (прогноз): нет данных',text)
if __name__=='__main__':unittest.main()
