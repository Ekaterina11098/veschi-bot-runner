import unittest,sys,types
from datetime import date
import china_buyer_price_forecast
if 'china_agent' not in sys.modules:sys.modules['china_agent']=types.ModuleType('china_agent')
sys.modules['china_agent.buyer_price_forecast']=china_buyer_price_forecast
from china_price_brief import render_plain,plain_payload
DAY=date(2026,10,19)
CAT=dict(cabinet='token_3',rows=[dict(vendorCode='590-PamelaBag-brown',nmID=1473245510),dict(vendorCode='123-Zont-pink',nmID=1556488210)])
BUYER=dict(report_date=str(DAY),status='available',rows={'1473245510':dict(article='590-PamelaBag-brown',current_cny='341.1',buyer_rub='3714'),'1556488210':dict(article='123-Zont-pink',current_cny='106.6',buyer_rub='1160')})
REVIEW=dict(report_date=str(DAY),status='complete_disclosed_forecast_model',model_version='wb_four_day_baseline_daily_means_v3',products=[dict(article='123-Zont-pink',after_price=106.6,before_price=82,full_days=4,result=dict(status='rollback_review'))])
EXPECTED='Повышение · 590-PamelaBag-brown Продавец: 341,1 → 375,3 ¥\nПокупатель: 3 714 → 4 086 ₽\n\nСнижение · 123-Zont-pink Продавец: 106,6 → 82 ¥\nПокупатель: 1 160 → 892 ₽'
MORNING='ПЕРВОЕ ПОВЫШЕНИЕ +10%: 1\n\n590-PamelaBag-brown\nЗаказы по дням: 1/3/1/1; отмены: 0.\nЦена продавца после скидки: 341,1 → 375,3 ¥.\nПовторное повышение'
INTRADAY='Первое повышение +10%: 1 кандидатов.\n• 590-PamelaBag-brown: заказы 3/1/1/1.\n  Предложение: 341,1 → 375,3 ¥ после скидки, с округлением.'
class PlainTests(unittest.TestCase):
 def test_morning_exact_approved_format(self):
  self.assertEqual(render_plain(MORNING,'morning',REVIEW,DAY,CAT,BUYER),EXPECTED)
 def test_intraday_exact_approved_format(self):
  self.assertEqual(render_plain(INTRADAY,'intraday',REVIEW,DAY,CAT,BUYER),EXPECTED)
 def test_product_links_and_bold_pairs(self):
  payload=plain_payload(EXPECTED,CAT);raw=EXPECTED.encode('utf-16-le')
  linked=[(raw[e['offset']*2:(e['offset']+e['length'])*2].decode('utf-16-le'),e['url']) for e in payload['entities'] if e['type']=='text_link']
  self.assertEqual(linked,[('590-PamelaBag-brown','https://www.wildberries.ru/catalog/1473245510/detail.aspx'),('123-Zont-pink','https://www.wildberries.ru/catalog/1556488210/detail.aspx')])
  self.assertEqual(sum(e['type']=='bold' for e in payload['entities']),6)
  self.assertEqual(payload['reply_markup']['inline_keyboard'],[])
 def test_buyer_only_continuation(self):
  self.assertEqual(plain_payload('Покупатель: 3 714 → 4 086 ₽',CAT)['entities'][0]['type'],'bold')
 def test_missing_buyer_is_not_zero(self):
  self.assertIn('Покупатель: нет данных',render_plain(MORNING,'morning',REVIEW,DAY,CAT,{}))
 def test_missing_review_is_not_no_candidates(self):
  self.assertTrue(render_plain(MORNING,'morning',None,DAY,CAT,BUYER).endswith('Снижение: нет данных'))
 def test_unrelated_text_not_reformatted(self):
  self.assertIsNone(plain_payload('Обычный вопрос',{}))
if __name__=='__main__':unittest.main()
