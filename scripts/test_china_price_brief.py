import unittest
from datetime import date
from china_price_brief import render,copy_entities,catalogue_ids
DAY=date(2026,10,19)
CAT=dict(cabinet='token_3',rows=[dict(vendorCode=a,nmID=n) for a,n in [('590-PamelaBag-brown',1473245510),('123-Zont-pink',1556488210),('15-FurPanama-cream',1535337778)]])
def review(status='rollback_review',days=4):
 return dict(report_date=str(DAY),status='complete_disclosed_forecast_model',
 model_version='wb_four_day_baseline_daily_means_v3',products=[
 dict(article='123-Zont-pink',after_price=106.6,before_price=82,full_days=days,result=dict(status=status))])
class BriefTests(unittest.TestCase):
 def test_morning(self):
  source='ПЕРВОЕ ПОВЫШЕНИЕ +10%: 1\n\n590-PamelaBag-brown\nЗаказы по дням: 1/3/1/1; отмены: 0.\nЦена продавца после скидки: 341,1 → 375,3 ¥.\nОбъяснение\nПовторное повышение\nПРОВЕРКА ВОЗМОЖНОГО СНИЖЕНИЯ'
  self.assertEqual(render(source,'morning',review(),DAY,CAT),'Рекомендации к повышению:\n590-PamelaBag-brown: 341,1 → 375,3 ¥\nАртикул WB: 1473245510\n\nРекомендации к снижению:\n123-Zont-pink: 106,6 → 82 ¥\nАртикул WB: 1556488210')
 def test_intraday(self):
  source='Первое повышение +10%: 1 кандидатов.\n• 15-FurPanama-cream: заказы 1/1/2/1.\n  Предложение: 79 → 87 ¥ после скидки, с округлением.\nБлижайшие кандидаты — ждём сегодняшний заказ:\n• OTHER: 1/1/1/0.'
  self.assertEqual(render(source,'intraday',review('investigate'),DAY,CAT),'Рекомендации к повышению:\n15-FurPanama-cream: 79 → 87 ¥\nАртикул WB: 1535337778\n\nРекомендации к снижению:\nНет')
 def test_missing_is_not_zero(self):
  self.assertTrue(render('Первое повышение +10%: 0 кандидатов.','intraday',None,DAY,CAT).endswith('Рекомендации к снижению:\nНет данных'))
 def test_stale_review(self):
  old=review();old['report_date']='2026-10-18'
  self.assertIn('Нет данных',render('ПЕРВОЕ ПОВЫШЕНИЕ +10%: 0','morning',old,DAY,CAT))
 def test_partial_rollback_rejected(self):
  with self.assertRaises(RuntimeError):render('ПЕРВОЕ ПОВЫШЕНИЕ +10%: 0','morning',review(days=3),DAY,CAT)
 def test_missing_proposal_rejected(self):
  with self.assertRaises(RuntimeError):render('ПЕРВОЕ ПОВЫШЕНИЕ +10%: 1','morning',review(),DAY,CAT)
 def test_unknown_source_fails_closed(self):
  with self.assertRaises(RuntimeError):render('Проверка не завершена','intraday',review(),DAY,CAT)
 def test_code_offsets_utf16(self):
  text='👜 Рекомендации\nАртикул WB: 1535337778'
  entity=copy_entities(text)[0]
  encoded=text.encode('utf-16-le')
  self.assertEqual(encoded[entity['offset']*2:(entity['offset']+entity['length'])*2].decode('utf-16-le'),'1535337778')
  self.assertEqual(entity['type'],'code')
 def test_unknown_id_not_guessed(self):
  with self.assertRaises(RuntimeError):render('ПЕРВОЕ ПОВЫШЕНИЕ +10%: 0','morning',review(),DAY,dict(cabinet='token_3',rows=[]))
 def test_ambiguous_id_rejected(self):
  with self.assertRaises(RuntimeError):catalogue_ids(dict(cabinet='token_3',rows=[dict(vendorCode='A',nmID=123),dict(vendorCode='a',nmID=456)]))
if __name__=='__main__':unittest.main()
