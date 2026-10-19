import unittest
from datetime import date
from china_price_brief import render
DAY=date(2026,10,19)
def review(status='rollback_review',days=4):
 return dict(report_date=str(DAY),status='complete_disclosed_forecast_model',
 model_version='wb_four_day_baseline_daily_means_v3',products=[
 dict(article='123-Zont-pink',after_price=106.6,before_price=82,full_days=days,result=dict(status=status))])
class BriefTests(unittest.TestCase):
 def test_morning(self):
  source='ПЕРВОЕ ПОВЫШЕНИЕ +10%: 1\n\n590-PamelaBag-brown\nЗаказы по дням: 1/3/1/1; отмены: 0.\nЦена продавца после скидки: 341,1 → 375,3 ¥.\nОбъяснение\nПовторное повышение\nПРОВЕРКА ВОЗМОЖНОГО СНИЖЕНИЯ'
  self.assertEqual(render(source,'morning',review(),DAY),'Повышение:\n590-PamelaBag-brown: 341,1 → 375,3 ¥\n\nСнижение:\n123-Zont-pink: 106,6 → 82 ¥')
 def test_intraday(self):
  source='Первое повышение +10%: 1 кандидатов.\n• 15-FurPanama-cream: заказы 1/1/2/1.\n  Предложение: 79 → 87 ¥ после скидки, с округлением.\nБлижайшие кандидаты — ждём сегодняшний заказ:\n• OTHER: 1/1/1/0.'
  self.assertEqual(render(source,'intraday',review('investigate'),DAY),'Повышение:\n15-FurPanama-cream: 79 → 87 ¥\n\nСнижение:\nНет')
 def test_missing_is_not_zero(self):
  self.assertTrue(render('Первое повышение +10%: 0 кандидатов.','intraday',None,DAY).endswith('Снижение:\nНет данных'))
 def test_stale_review(self):
  old=review();old['report_date']='2026-10-18'
  self.assertIn('Нет данных',render('ПЕРВОЕ ПОВЫШЕНИЕ +10%: 0','morning',old,DAY))
 def test_partial_rollback_rejected(self):
  with self.assertRaises(RuntimeError):render('ПЕРВОЕ ПОВЫШЕНИЕ +10%: 0','morning',review(days=3),DAY)
 def test_missing_proposal_rejected(self):
  with self.assertRaises(RuntimeError):render('ПЕРВОЕ ПОВЫШЕНИЕ +10%: 1','morning',review(),DAY)
 def test_unknown_source_fails_closed(self):
  with self.assertRaises(RuntimeError):render('Проверка не завершена','intraday',review(),DAY)
if __name__=='__main__':unittest.main()
