import unittest
from datetime import date
from china_price_brief import lowering,raising,render_plain
DAY=date(2026,10,20)
def review():
 return dict(report_date=str(DAY),status='complete_disclosed_forecast_model',model_version='wb_four_day_baseline_daily_means_v3',products=[dict(article='A',before_price=75,after_price=97.5,full_days=4,result={'status':'rollback_review'})])
def cat():
 return dict(cabinet='token_3',rows=[dict(vendorCode='A',nmID=1,currencyIsoCode4217='CNY',discount=50,sizes=[dict(price=195,discountedPrice=97.5)])])
class StepTests(unittest.TestCase):
 def test_decrease_from_current_not_historical(self):
  self.assertEqual(lowering(review(),DAY,cat()),[('A','97,5','93')])
 def test_stale_current_fails_closed(self):
  c=cat();c['rows'][0]['sizes'][0]['discountedPrice']=98
  omitted=[]
  self.assertEqual(lowering(review(),DAY,c,omitted),[])
  self.assertEqual(omitted[0]['status'],'price_changed_since_review')
 def test_no_unknown_base_guess(self):
  with self.assertRaises(RuntimeError):lowering(review(),DAY,{})
 def test_five_percent_heading_both_reports(self):
  self.assertEqual(raising('ПЕРВОЕ ПОВЫШЕНИЕ +5%: 0','morning'),[])
  self.assertEqual(raising('Первое повышение +5%: 0 кандидатов','intraday'),[])
 def test_applied_cut_does_not_block_other_raises(self):
  import sys,types
  import china_buyer_price_forecast as forecast
  sys.modules.setdefault('china_agent',types.ModuleType('china_agent'))
  sys.modules['china_agent.buyer_price_forecast']=forecast
  c=cat();c['rows'][0]['sizes'][0].update(price=186,discountedPrice=93)
  c['rows'].append(dict(vendorCode='B',nmID=2))
  source='Первое повышение +5%: 1 кандидатов.\n• B: заказы 1/1/1/1.\n  Предложение: 100 → 105 ¥ после скидки'
  excluded=[]
  text=render_plain(source,'intraday',review(),DAY,c,{},omitted=excluded)
  self.assertIn('Повышение · B Продавец: 100 → 105 ¥',text)
  self.assertNotIn('Снижение · A',text)
  self.assertEqual(len(excluded),1)
if __name__=='__main__':unittest.main()

