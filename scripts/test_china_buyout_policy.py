import copy,sys,types,unittest
from datetime import datetime,timezone
from decimal import Decimal
from unittest.mock import patch
from china_expected_order_profit import buyout_from_product,resolved_buyout_rate
from china_break_even import calculate,resolve,answer,compact_report,compact_payload
NM='1473243898';ART='119-NoelBag-darkblack'
PRODUCT=dict(nm_id=int(NM),sa_name=ART,p_id=1,is_payed=1,finish_as_return=0,finished_orders=3,is_payed_percent_after_returns=33.33,orders_count=4,advertisement=0,sales_ret_sum=2293.83,total_commission_without_spp=458.82,acquiring=0,sales_sum=1903.96,returns_sum=0,taxes=95.2,price_after_spp=1594,deduction=0,penalty=0,storage_fee=0,acceptance=0,total_cashback=0)
class Fake:
 def __init__(self):
  self.now=datetime(2026,10,20,12,tzinfo=timezone.utc);self.calls=[]
  self.product=copy.deepcopy(PRODUCT)
  self.raw=[dict(nmId=int(NM),vendorCode=ART,rrdId=1,rrDate='2026-10-13',sellerOperName='销售',commissionPercent=20,acquiringFee=0)]+[dict(nmId=int(NM),vendorCode=ART,rrdId=i,rrDate='2026-10-13',sellerOperName='配送',deliveryService='15.5') for i in range(2,6)]
  self.cache={'china_agent:prices:v1':dict(cabinet='token_3',observed_at='2026-10-20T11:08:00+03:00',rows=[dict(nmID=int(NM),vendorCode=ART,currencyIsoCode4217='CNY',discount=60,sizes=[dict(discountedPrice=146.4)])]),
   'china_agent:expected_profit_delivery_model:v1':dict(cabinet='token_3',rub_per_cny=12,acceptance_rub_per_dispatch=10,rows={ART:dict(delivery_cny=16)}),
   'page':dict(cabinet='token_3',rows=self.raw)}
 def catalog(self):return [(NM,ART)]
 def get(self,key):return self.cache.get(key)
 def db(self,method,table,params=None,**kw):
  assert method=='GET';self.calls.append((table,params))
  if table=='analytics_costs':return [dict(cost=869.2275752773376)]
  if table=='telegram_api_cache':
   key=params['cache_key']
   if 'commission_return_audit' in key:return [dict(cache_key='finance',payload=dict(status='complete',cabinet='token_3',terminal_204=True,period_from='2026-09-20',period_to='2026-10-19',pages=[dict(cache_key='page',rows=5)],row_count=5))]
   if 'economics_audit' in key:
    from datetime import date,timedelta
    daily={str(date(2026,9,20)+timedelta(days=i)):dict(deduction=19329.76 if i==0 else 0) for i in range(30)}
    return [dict(cache_key='economics',payload=dict(extra_reads=dict(cabinet='token_3',reports=dict(lk_wb_dashboard_table=dict(data=dict(data=daily))))))]
  raise AssertionError((table,params))
 def run(self):
  module=types.ModuleType('analytics.mpstats_primary')
  module.products=lambda *a:([self.product,dict(nm_id=2,sa_name='OTHER',orders_count=1180,deduction=0)],dict(id=18691))
  with patch.dict(sys.modules,{'analytics.mpstats_primary':module}):
   return answer(self,dict(request_text='Рассчитай цену безубыточности с учетом всех расходов включая рекламу на 119 артикул'))
class PolicyTests(unittest.TestCase):
 def test_119_uses_one_of_three_not_fifty(self):
  r=buyout_from_product(PRODUCT);self.assertEqual(r['probability'],Decimal(1)/3);self.assertEqual(r['sample_size'],3)
 def test_returns_already_excluded(self):
  p=dict(PRODUCT,is_payed=6,finish_as_return=1,finished_orders=11,is_payed_percent_after_returns=54.55)
  self.assertEqual(buyout_from_product(p)['probability'],Decimal(6)/11)
 def test_real_zero_never_fallback(self):
  p=dict(PRODUCT,is_payed=0,finish_as_return=1,finished_orders=1,is_payed_percent_after_returns=0)
  r=buyout_from_product(p);self.assertEqual(r['percent'],0);self.assertEqual(r['source'],'own_article')
 def test_only_empty_sample_fallback(self):
  p=dict(PRODUCT,is_payed=0,finish_as_return=0,finished_orders=0,is_payed_percent_after_returns=0)
  self.assertEqual(buyout_from_product(p)['source'],'fallback')
 def test_partial_or_inconsistent_never_fallback(self):
  for p in [dict(PRODUCT,finished_orders=None),dict(PRODUCT,is_payed_percent_after_returns=50),dict(PRODUCT,finished_orders=0)]:
   with self.assertRaises(ValueError):buyout_from_product(p)
 def test_short_article_is_resolved_first(self):
  self.assertEqual(resolve('Безубыточность 119 артикул',[(NM,ART)])[0],NM)
 def test_ambiguous_short_article(self):
  with self.assertRaises(ValueError):resolve('119 артикул',[(NM,ART),('2','119-OTHER')])
 def test_two_scenarios_actual_rate_and_order_based_drr(self):
  w=Fake();text,trace=w.run();r=trace[0]
  self.assertEqual(r['buyout']['sample_size'],3);self.assertAlmostEqual(r['buyout']['percent'],100/3)
  self.assertEqual(len(r['scenarios']),2);self.assertGreater(r['scenarios'][1]['seller_after_cny'],r['scenarios'][0]['seller_after_cny'])
  self.assertIn('33,3%',text);self.assertIn('ДРР 5% от заказов',text);self.assertEqual(r['ads'],0)
 def test_zero_percent_no_finite_price(self):
  w=Fake();w.product.update(is_payed=0,finished_orders=3,is_payed_percent_after_returns=0)
  text,trace=w.run();self.assertTrue(all(r['status']=='no_finite_break_even' for r in trace[0]['scenarios']))
 def test_missing_cost_not_zero(self):
  w=Fake();old=w.db
  w.db=lambda method,table,**kw:[] if table=='analytics_costs' else old(method,table,**kw)
  self.assertEqual(w.run()[1][0]['status'],'incomplete')
 def test_stale_current_price_fails_closed(self):
  w=Fake();w.cache['china_agent:prices:v1']['observed_at']='2026-10-19T11:08:00+03:00'
  self.assertEqual(w.run()[1][0]['status'],'incomplete')
 def test_rounding_keeps_discount_and_prevents_loss(self):
  p=Decimal(1)/3;result=calculate('869.2275752773376',196,0,Decimal('19329.76')/1184,p,'.2','.05',Decimal(1594)/(Decimal('146.4')*12),12,60)
  for r in result:
   price=Decimal(str(r['seller_after_cny']))*12
   drr=Decimal('.05') if r['scenario']=='drr5_orders' else 0
   profit=p*(price*(1-Decimal('.2')-Decimal('.05')*Decimal(1594)/(Decimal('146.4')*12))-Decimal('869.2275752773376'))-196-Decimal('19329.76')/1184-price*drr
   self.assertGreaterEqual(profit,0)
   self.assertAlmostEqual(r['seller_after_cny'],r['base_cny']*.4)
class CompactTests(unittest.TestCase):
 def test_short_approved_layout_and_links(self):
  text,trace=Fake().run()
  self.assertLess(len(text),600);self.assertNotIn('Учтено:',text)
  self.assertIn('Нынешняя реклама: 166,4 ¥',text)
  self.assertIn('ДРР 5% от заказов: 207,6 ¥',text)
  self.assertIn('33,3% · 1 из 3, выборка мала',text)
  payload=compact_payload(text,[(NM,ART)])
  self.assertEqual(payload['entities'][0]['url'],'https://www.wildberries.ru/catalog/'+NM+'/detail.aspx')
  self.assertEqual(trace[0]['inputs']['cost_rub'],869.2275752773376)
 def test_fallback_explicit(self):
  w=Fake();w.product.update(is_payed=0,finish_as_return=0,finished_orders=0,is_payed_percent_after_returns=0)
  self.assertIn('50% · принято для расчёта',w.run()[0])
 def test_generic_message_not_formatted(self):
  self.assertEqual(compact_payload('Обычный вопрос',[]),{})
class InitialPriceTests(unittest.TestCase):
 def test_initial_price_uses_actual_small_sample(self):
  import importlib.util
  from pathlib import Path
  policy=sys.modules['china_expected_order_profit']
  package=types.ModuleType('buyout_fixture');package.__path__=[]
  spec=importlib.util.spec_from_file_location('buyout_fixture.core',Path(__file__).with_name('china_core_buyout.py'))
  core=importlib.util.module_from_spec(spec)
  with patch.dict(sys.modules,{'buyout_fixture':package,'buyout_fixture.expected_order_profit':policy}):
   spec.loader.exec_module(core)
   profile={'economics':{'model_version':'test','unresolved':[], 'parameters':{k:{'value':v} for k,v in dict(buyout_rate=.5,rub_per_cny=12,commission_rate=.28,acquiring_rate=.03,target_profit_on_cost=.3,acceptance_rub_per_dispatch=10).items()}}}
   core.load_profile=lambda:copy.deepcopy(profile)
   actual=core.forecast_price(869.23,186,buyout_stats=PRODUCT)
   empty=core.forecast_price(869.23,186,buyout_stats=dict(PRODUCT,is_payed=0,finish_as_return=0,finished_orders=0,is_payed_percent_after_returns=0))
   self.assertGreater(actual['seller_price_after_discount_cny'],empty['seller_price_after_discount_cny'])
   self.assertEqual(actual['parameters']['buyout_rate']['sample_size'],3)
   with self.assertRaises(TypeError):core.forecast_price(869.23,186)
   with self.assertRaises(ValueError):core.forecast_price(869.23,186,buyout_stats=dict(PRODUCT,is_payed=0,finished_orders=3,is_payed_percent_after_returns=0))
if __name__=='__main__':unittest.main()

