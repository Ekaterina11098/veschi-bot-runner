import copy,unittest
from datetime import datetime,timezone
from unittest.mock import patch
from china_product_current import read_prices,scoped
from china_ad_expense_table import table,requested

def price(nm=1,p=126):return dict(nmID=nm,vendorCode='test',currencyIsoCode4217='CNY',discount=50,sizes=[dict(sizeID=9,discountedPrice=p)])
class InputTests(unittest.TestCase):
 def test_exact_price_does_not_request_whole_catalogue(self):
  calls=[]
  def get(url,args):calls.append(args);return dict(data=dict(listGoods=[price(args['filterNmID'])]))
  rows=read_prices(get,[2,1])['rows'];self.assertEqual([r['nm_id'] for r in rows],[1,2]);self.assertTrue(all('filterNmID' in a for a in calls))
 def test_full_price_pages_supported(self):
  calls=[]
  def get(url,args):
   calls.append(args['offset']);return dict(data=dict(listGoods=[price(i+1) for i in range(1000)] if args['offset']==0 else [price(1001)]))
  self.assertEqual(len(read_prices(get,[])['rows']),1001);self.assertEqual(calls,[0,1000])
 def test_wrong_id_currency_and_multiple_size_price_rejected(self):
  for r in [price(2),dict(price(),currencyIsoCode4217='RUB'),dict(price(),sizes=[dict(discountedPrice=126),dict(discountedPrice=127)])]:
   with self.assertRaises(ValueError):read_prices(lambda *a:dict(data=dict(listGoods=[r])),[1])
 def test_empty_exact_price_not_zero(self):
  with self.assertRaises(ValueError):read_prices(lambda *a:dict(data=dict(listGoods=[])),[1])
 def test_diagnostic_scoped_reads_not_exhausted_by_llm_budget(self):
  from types import SimpleNamespace
  data={};calls=[]
  def collect(topic,ids,first,last):calls.append((topic,ids));return dict(source='test',rows=[dict(nm_id=1)])
  w=SimpleNamespace(now=datetime.now(timezone.utc),get=lambda key:data.get(key),save=lambda k,v:data.update({k:v}))
  a=SimpleNamespace(w=w,fresh_reads=3,collect=collect)
  first=scoped(a,'prices',[1],'2026-10-28','2026-10-30');w.now=datetime.now(timezone.utc)
  self.assertEqual(scoped(a,'prices',[1],'2026-10-28','2026-10-30'),first);self.assertEqual(calls,[('prices',[1])])

class ExpenseQuestionTests(unittest.TestCase):
 def stats(self):
  ns=[dict(nmId=1,sum=10,sum_price=0,orders=0),dict(nmId=2,sum=30,sum_price=0,orders=0),dict(nmId=3,sum=5,sum_price=10,orders=1),dict(nmId=4,sum=100,sum_price=1000,orders=2)]
  return [dict(advertId=12,days=[dict(apps=[dict(nms=ns)])])]
 def test_no_orders_before_high_drr_then_descending(self):
  rows,missing=table(self.stats(),{i:str(i) for i in range(1,5)})
  self.assertEqual([r['nm_id'] for r in rows],[2,1,3,4]);self.assertIsNone(rows[0]['drr']);self.assertEqual(rows[2]['drr'],50)
 def test_threshold_does_not_lose_no_order_cost(self):
  rows,_=table(self.stats(),{i:str(i) for i in range(1,5)},11)
  self.assertEqual([r['nm_id'] for r in rows],[2,1,3])
 def test_app_campaign_sums_once_no_top_level_double_count(self):
  s=self.stats();s[0]['sum']=99999;s[0]['days'][0]['sum']=99999
  rows,_=table(s,{i:str(i) for i in range(1,5)});self.assertEqual(sum(r['spend'] for r in rows),145)
 def test_unknown_counter_not_zero(self):
  s=self.stats();del s[0]['days'][0]['apps'][0]['nms'][0]['sum']
  with self.assertRaises(ValueError):table(s,{i:str(i) for i in range(1,5)})
 def test_unknown_article_disclosed(self):
  rows,missing=table(self.stats(),{1:'one'});self.assertEqual(missing,[2,3,4]);self.assertEqual(len(rows),1)
 def test_data_questions_do_not_route_to_bid_diagnosis(self):
  for q in ['Есть лидеры кто тянет большой расход с высоким дрр выше 10%? Артикулы','Дай таблицу с колонками: артикул, траты сегодня, дрр. Отсортируй по дорогому дрр сверху вниз']:
   self.assertTrue(requested(q))
  self.assertTrue(requested('Хочу сам посмотреть',[dict(request_text='Таблица ДРР')]))
  self.assertFalse(requested('Сделай пополнение по таблице ДРР'))

if __name__=='__main__':unittest.main()
