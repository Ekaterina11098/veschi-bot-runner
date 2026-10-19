import unittest,sys,types
from datetime import date
import china_buyer_price_forecast
if 'china_agent' not in sys.modules:sys.modules['china_agent']=types.ModuleType('china_agent')
sys.modules['china_agent.buyer_price_forecast']=china_buyer_price_forecast
from china_price_brief import render_table,table_payload
DAY=date(2026,10,19)
CAT=dict(cabinet='token_3',rows=[dict(vendorCode='51-NoelBag-green',nmID=1473243906),dict(vendorCode='123-Zont-pink',nmID=1556488210)])
BUYER=dict(report_date=str(DAY),status='available',rows={'1473243906':dict(article='51-NoelBag-green',current_cny='180',buyer_rub='1960'),'1556488210':dict(article='123-Zont-pink',current_cny='106.6',buyer_rub='1160')})
REVIEW=dict(report_date=str(DAY),status='complete_disclosed_forecast_model',model_version='wb_four_day_baseline_daily_means_v3',products=[dict(article='123-Zont-pink',after_price=106.6,before_price=82,full_days=4,result=dict(status='rollback_review'))])
SOURCE='Первое повышение +10%: 1 кандидатов.\n• 51-NoelBag-green: заказы 3/2/2/3.\n  Предложение: 180 → 198 ¥ после скидки, с округлением.'
class TableTests(unittest.TestCase):
 def text(self,buyer=BUYER,review=REVIEW):return render_table(SOURCE,'intraday',review,DAY,CAT,buyer)
 def test_one_table_all_five_price_fields(self):
  text=self.text()
  rows=[[v.strip() for v in line.split('|')] for line in text.splitlines() if line.startswith(('Повышение','Снижение'))]
  self.assertEqual(rows,[['Повышение','51-NoelBag-green','180','198','1 960','2 156'],['Снижение','123-Zont-pink','106,6','82','1 160','892']])
  self.assertEqual(text.count('Новая ₽ (прогноз)'),1)
 def test_product_navigation(self):
  payload=table_payload(self.text(),CAT)
  urls=[row[0]['url'] for row in payload['reply_markup']['inline_keyboard']]
  self.assertEqual(urls,['https://www.wildberries.ru/catalog/1473243906/detail.aspx','https://www.wildberries.ru/catalog/1556488210/detail.aspx'])
  self.assertEqual(payload['entities'][0]['type'],'pre')
 def test_continuation_part_keeps_navigation(self):
  continuation='\n'.join(line for line in self.text().splitlines() if line.startswith('Снижение'))
  self.assertEqual(len(table_payload(continuation,CAT)['reply_markup']['inline_keyboard']),1)
 def test_missing_buyer_not_zero(self):
  self.assertIn('нет данных',self.text(buyer={}))
 def test_missing_review_not_no_candidates(self):
  self.assertIn('Рекомендации к снижению: нет данных.',self.text(review=None))
 def test_unrelated_message_not_formatted(self):
  self.assertIsNone(table_payload('Обычный вопрос',{}))
if __name__=='__main__':unittest.main()
