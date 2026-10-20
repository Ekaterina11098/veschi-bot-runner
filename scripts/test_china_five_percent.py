import unittest
from datetime import date
from china_price_brief import lowering,raising
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
  with self.assertRaises(RuntimeError):lowering(review(),DAY,c)
 def test_no_unknown_base_guess(self):
  with self.assertRaises(RuntimeError):lowering(review(),DAY,{})
 def test_five_percent_heading_both_reports(self):
  self.assertEqual(raising('ПЕРВОЕ ПОВЫШЕНИЕ +5%: 0','morning'),[])
  self.assertEqual(raising('Первое повышение +5%: 0 кандидатов','intraday'),[])
if __name__=='__main__':unittest.main()
