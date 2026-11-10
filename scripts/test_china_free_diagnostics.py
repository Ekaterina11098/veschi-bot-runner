import copy,unittest
from datetime import datetime,timezone
from unittest.mock import patch
import china_free_diagnostics as d
import china_no_paid as free
import china_codex_cloud as cloud

NOW=datetime(2026,11,10,3,30,tzinfo=timezone.utc)
class W:
 now=NOW
 def __init__(self):self.values={};self.found=[]
 def get(self,k):return self.values.get(k)
 def save(self,k,v,**kw):self.values[k]=copy.deepcopy(v);return True
 def db(self,*a,**kw):return self.found
def stats(nm,spend,amount,orders):return dict(nmId=nm,sum=spend,sum_price=amount,orders=orders)
def data():
 return d.aggregate({1:9},{1:{'currency':'CNY'}},[dict(advertId=1,days=[dict(date='2026-11-09',apps=[dict(nms=[
  stats(1,500,5000,10),stats(2,10,1,1),stats(3,50,0,0)])])])],{'1':'big','2':'tiny','3':'zero'},'2026-11-07','2026-11-09')
class FreeDiagnostics(unittest.TestCase):
 def test_real_high_drr_question_is_not_new_campaign(self):
  text='Посмотри какие товары дают дрр большой? Средний дрр вырос, надо отсечь несколько самых дорогих товаров'
  self.assertEqual(d.intent(text),'drr')
  w=W()
  with patch.object(d,'collect',return_value=dict(data(),observed_at=NOW.isoformat())),patch('china_free_ads.handle',side_effect=AssertionError('Wrong acquisition route')):
   answer=free.safe_answer(w,dict(id=283,request_text=text,sender_id=5122667182))
  self.assertIn('big / 1',answer);self.assertFalse(any('new_ad_report_request' in k for k in w.values))
 def test_expense_contribution_not_maximum_percentage(self):
  r=data();self.assertEqual(r['rows'][0]['article'],'big')
  self.assertAlmostEqual(r['drr_pct'],100*560/5001)
  self.assertGreater(next(v['drr_pct']for v in r['rows']if v['article']=='tiny'),100)
 def test_zero_orders_are_not_zero_drr_or_cpa(self):
  row=next(r for r in data()['rows']if r['article']=='zero')
  self.assertIsNone(row['drr_pct']);self.assertIsNone(row['cpa_cny'])
 def test_mixed_currency_duplicate_campaign_and_outside_period_rejected(self):
  with self.assertRaises(ValueError):d.aggregate({1:9},{1:{'currency':'RUB'}},[dict(advertId=1,days=[])],{},'2026-11-07','2026-11-09')
  with self.assertRaises(ValueError):d.aggregate({1:9},{1:{'currency':'CNY'}},[dict(advertId=1,days=[])]*2,{},'2026-11-07','2026-11-09')
  with self.assertRaises(ValueError):d.aggregate({1:9},{1:{'currency':'CNY'}},[dict(advertId=1,days=[dict(date='2026-11-10',apps=[])])],{},'2026-11-07','2026-11-09')
 def test_missing_rows_not_assumed_zero_and_partial_scope_explicit(self):
  x=d.aggregate({1:9,2:11},{1:{'currency':'CNY'}},[dict(advertId=1,days=[dict(date='2026-11-09',apps=[dict(nms=[stats(1,None,5,1)])])])],{},'2026-11-07','2026-11-09')
  self.assertEqual(x['invalid_rows'],1);self.assertEqual(x['missing_campaign_ids'],[2])
 def test_new_candidate_request_keeps_acquisition_route(self):
  self.assertIsNone(d.intent('Покажи 20 кандидатов для рекламы при ДРР 5%'))
  self.assertIsNone(d.intent('Подготовь рекламный тест с экономикой'))
  self.assertIsNone(d.intent('Проверь минимальную цену безубыточности'))
 def test_missing_daily_economics_is_not_zero_cabinet_economics(self):
  w=W();w.found=[dict(payload=dict(observed_at='2026-11-09T04:19:17+00:00',economics={'rows':{'1':{},'2':{}}}),updated_at='2026-11-09T04:19:17+00:00')]
  text=d.coverage_answer(w);self.assertIn('не сохранён',text);self.assertIn('2026-11-09',text);self.assertIn('строк экономики 2',text)
 def test_minimum_request_never_claims_unverified_write(self):
  w=W();w.found=[dict(updated_at='2026-11-09T17:35:00+00:00',payload={'minimum_prices':dict(minimums_wb_verified=False,rows=[dict(article='56-Noel',minimum_cny=218)])})]
  text=d.minimum_answer(w,'Сделай минимальные цены и блокировки')
  self.assertIn('218',text);self.assertIn('Не подтверждена',text);self.assertIn('Автоматическая установка не выполнена',text)
 def test_network_scope_is_get_only_and_no_billing_endpoint(self):
  self.assertTrue(d.allowed_read('GET','https://advert-api.wildberries.ru/adv/v3/fullstats'))
  self.assertFalse(d.allowed_read('POST','https://advert-api.wildberries.ru/adv/v3/fullstats'))
  self.assertFalse(d.allowed_read('GET','https://api.openai.com/v1/responses'))
  self.assertFalse(d.allowed_read('POST','https://advert-api.wildberries.ru/adv/v1/budget/deposit'))
 def test_paid_lock_wins_over_inconsistent_policy_flags(self):
  w=W();w.values[free.POLICY]=dict(enabled=False,paid_api_allowed=True,owner_no_paid_lock=True,chat_id=free.CHAT,bot_id=free.BOT)
  self.assertTrue(free.enabled(w))
  with self.assertRaises(PermissionError):free.require_paid_api(dict(enabled=True,paid_api_allowed=True,chat_id=free.CHAT,bot_id=free.BOT,model='gpt-6.1-sol'))
 def test_completed_day_window_and_future_rejected(self):
  self.assertEqual(tuple(map(str,d.window(W(),'ДРР вырос'))),('2026-11-07','2026-11-09'))
  with self.assertRaises(ValueError):d.window(W(),'ДРР 2026-11-11')
  with self.assertRaises(ValueError):d.window(W(),'ДРР за 30 дней')
if __name__=='__main__':unittest.main()
