import copy,sys,types,unittest
from datetime import date,datetime,timezone
from unittest.mock import patch
import china_profit_forecast as p
DAY=date(2026,10,31)
CLOCK=datetime(2026,10,31,20,15,tzinfo=timezone.utc)

def fixture():
 return dict(cabinet='token_3',inputs=dict(
  orders=dict(complete=True,cutoff_msk='2026-10-31T23:09:35+03:00',rows=[dict(id=1,nmId=143,article='143-Bag-black',createdAt='2026-10-31T09:00:00Z',convertedPrice=999999)]),
  statuses=dict(complete=True,rows=[dict(id=1,wbStatus='waiting',supplierStatus='new')]),
  fx=dict(rub_per_cny='12',effective_date='2026-10-31'),
  own_products=dict(rows=[dict(nm_id=143,is_payed=1,finished_orders=2,finish_as_return=0,cost_price=240,total_commission_without_spp_in_sales=20)]),
  prices=dict(rows=[dict(nm_id=143,article='143-Bag-black',currency='CNY',seller_price=100)]),
  stock=dict(rows=[dict(article='143-Bag-black',price=24000)]),
  advertising=dict(all_statuses_included=True,catalogue=[4,9],rows=[dict(advertId=4,currency='CNY',days=[dict(date=str(DAY),sum=3,apps=[dict(appType=1,nms=[dict(nmId=143,sum=3)])])]),dict(advertId=9,status=7,currency='CNY',days=[dict(date=str(DAY),sum=2,apps=[dict(appType=1,nms=[dict(nmId=143,sum=2)])])])])
 ))
POLICY=dict(commission_pct=20,tax_pct=5,handling_rub=12,logistics_by_nm={'143':dict(delivery_cny=3)})
def calc(f=None):return p.calculate(f or fixture(),POLICY,{},DAY)

class Model(unittest.TestCase):
 def test_accounting_and_closed_ads(self):
  r=calc();self.assertEqual(r['totals']['forecast_profit_cny'],18.5)
  self.assertEqual(r['totals']['advertising_cny'],5)
  self.assertEqual(r['totals']['expected_seller_revenue_cny'],50)
  self.assertFalse(r['is_actual']);self.assertFalse(r['grants_action_permission'])
 def test_declined_cancelled_all_spellings(self):
  for status in p.CANCELLED:
   with self.subTest(status=status):
    f=fixture();f['inputs']['statuses']['rows'][0]['wbStatus']=status;r=calc(f)
    self.assertEqual(r['totals']['cancelled_orders'],1);self.assertEqual(r['totals']['forecast_profit_cny'],-9)
 def test_supplier_cancel(self):
  f=fixture();f['inputs']['statuses']['rows'][0]['supplierStatus']='cancel';self.assertEqual(calc(f)['totals']['expected_buyouts'],0)
 def test_true_zero_is_not_fifty(self):
  f=fixture();f['inputs']['own_products']['rows'][0]['is_payed']=0;r=calc(f)
  self.assertEqual(r['totals']['expected_buyouts'],0);self.assertNotIn('buyout50_orders',r['fallbacks'])
 def test_no_completed_sample_fifty_explicit(self):
  f=fixture();f['inputs']['own_products']['rows'][0].update(is_payed=0,finished_orders=0)
  r=calc(f);self.assertEqual(r['fallbacks']['buyout50_orders'],1);self.assertIn('допущение50%',p.render(r))
 def test_pending_never_in_denominator(self):
  f=fixture();f['inputs']['own_products']['rows'][0]['not_finished_orders']=9999
  self.assertEqual(calc(f)['totals']['expected_buyouts'],.5)
 def test_sold_is_one_not_probability(self):
  f=fixture();f['inputs']['statuses']['rows'][0]['wbStatus']='sold';self.assertEqual(calc(f)['totals']['expected_buyouts'],1)
 def test_returns_not_subtracted_twice(self):
  f=fixture();f['inputs']['own_products']['rows'][0].update(finish_as_return=1)
  self.assertEqual(calc(f)['totals']['expected_buyouts'],.5)
 def test_missing_price_status_cost_never_total(self):
  for name in ['prices','statuses','own_products']:
   f=fixture();f['inputs'][name]['rows']=[];r=calc(f)
   self.assertIsNone(r['totals']['forecast_profit_cny']);self.assertEqual(r['modelled_orders'],0)
 def test_stock_cost_fallback_declared(self):
  f=fixture();f['inputs']['stock']['rows']=[];r=calc(f)
  self.assertEqual(r['fallbacks']['cogs_own_mpstats_orders'],1);self.assertEqual(r['totals']['cogs_cny'],10)
 def test_missing_all_cogs(self):
  f=fixture();f['inputs']['stock']['rows']=[];f['inputs']['own_products']['rows'][0].pop('cost_price')
  self.assertIsNone(calc(f)['totals']['forecast_profit_cny'])
 def test_ads_missing_unknown_currency_not_zero(self):
  for field in ['currency','days']:
   f=fixture();f['inputs']['advertising']['rows'][0].pop(field);r=calc(f)
   self.assertIsNone(r['totals']['forecast_profit_cny']);self.assertIsNone(r['totals']['advertising_cny'])
 def test_missing_campaign_flagged(self):
  f=fixture();f['inputs']['advertising']['catalogue'].append(90);r=calc(f)
  self.assertEqual(r['missing_ad_campaigns'],[90]);self.assertIn('расходы по ним неизвестны',p.render(r))
 def test_duplicate_ads_rejected(self):
  f=fixture();f['inputs']['advertising']['rows']*=2;self.assertIsNone(calc(f)['totals']['forecast_profit_cny'])
 def test_duplicate_order_rejected(self):
  f=fixture();f['inputs']['orders']['rows']*=2
  with self.assertRaises(ValueError):calc(f)
 def test_wrong_date_fx_and_cabinet(self):
  for mutate in [lambda f:f.update(cabinet='token_1'),lambda f:f['inputs']['fx'].update(effective_date='2026-11-01'),lambda f:f['inputs']['orders'].update(complete=False)]:
   f=fixture();mutate(f)
   with self.assertRaises(ValueError):calc(f)
 def test_no_orders_still_deduct_ads(self):
  f=fixture();f['inputs']['orders']['rows']=[];r=calc(f);self.assertEqual(r['totals']['forecast_profit_cny'],-5);self.assertIn('-5.00',p.render(r))
 def test_selected_scope_uses_sku_not_campaign_cost(self):
  f=fixture();f['inputs']['advertising']['rows'][0]['days'][0]['sum']=100
  r=p.calculate(f,POLICY,{},DAY,[143]);self.assertEqual(r['totals']['advertising_cny'],5)
 def test_finance_only_other_charges_no_forpay_double_subtraction(self):
  f=fixture();f['inputs']['finance']=dict(cabinet='token_3',period_from=str(DAY),period_to=str(DAY),complete=True,rows=[
   dict(rrdId=1,rrDate=str(DAY),currency='CNY',forPay=1000,deliveryService=100,paidStorage=1,paidAcceptance=2,penalty=3,deduction=50,bonusTypeName='WB Promotion',additionalPayment=4),
   dict(rrdId=2,rrDate=str(DAY),currency='CNY',deduction=5,bonusTypeName='Confirmed service')])
  r=calc(f);self.assertEqual(r['totals']['known_other_costs_cny'],11);self.assertEqual(r['totals']['forecast_profit_cny'],11.5)
 def test_unclassified_deduction_cannot_double_ads(self):
  f=fixture();f['inputs']['finance']=dict(cabinet='token_3',period_from=str(DAY),period_to=str(DAY),rows=[dict(rrdId=1,rrDate=str(DAY),currency='CNY',deduction=50)])
  self.assertIsNone(calc(f)['totals']['forecast_profit_cny'])
 def test_external_expenses_currency_and_inclusion(self):
  f=fixture();f['inputs']['external_costs']=dict(cabinet='token_3',date_msk=str(DAY),complete=False,rows=[
   dict(id='a',source_ref='owner-receipt',kind='expense',amount=24,currency='RUB',included_in='additional'),
   dict(id='b',source_ref='ad-source',kind='expense',amount=100,currency='CNY',included_in='advertising')])
  self.assertEqual(calc(f)['totals']['forecast_profit_cny'],16.5)
 def test_unknown_expenses_disclosed(self):
  r=calc();self.assertFalse(r['known_charges']['complete']);self.assertIn('не опубликована',p.render(r));self.assertIn('не закрытая',p.render(r))

class W:
 now=CLOCK
 def __init__(self):self.mem={};self.writes=[]
 def get(self,k):return copy.deepcopy(self.mem.get(k))
 def save(self,k,v):self.mem[k]=copy.deepcopy(v);self.writes.append(k)
 def catalog(self):return [('143','143-Bag-black')]

class Routes(unittest.TestCase):
 def test_requests(self):
  for t in ['Посчитай предварительную прибыль на сегодня','Сколько сегодня заработали?','Прибыль за вчера','сколько прибыли по этой модели?']:self.assertTrue(p.requested(t),t)
  for t in ['Научи агента считать прибыль','Как рассчитать прибыль?','Сравни прибыль за неделю','сколько заказов сегодня']:self.assertFalse(p.requested(t),t)
 def test_fresh_and_future(self):
  for at,expected in [('2026-10-31T20:10:00+00:00',True),('2026-10-31T20:16:00+00:00',False),('2026-10-31T19:00:00+00:00',False)]:self.assertEqual(p.fresh(dict(cabinet='token_3',observed_at=at),CLOCK,600),expected)
 def test_real_route_saves_readback(self):
  import china_analytic_dialog as d
  w=W();w.mem[d.POLICY]={'enabled':True};w.mem['china_agent:new_ad_economics_policy:v1']=POLICY
  with patch.object(p,'collect',return_value=(fixture(),'private-fixture')):
   answer,trace=d.answer(w,dict(id=900,request_text='Посчитай предварительную прибыль на сегодня'),[])
  self.assertIn('18.50',answer);self.assertEqual(trace[0]['name'],'calculate_preliminary_profit');self.assertTrue(w.writes)
 def test_disabled_policy_no_collection(self):
  import china_analytic_dialog as d
  with patch.object(p,'collect') as read:self.assertIsNone(d.answer(W(),dict(request_text='Посчитай прибыль сегодня'),[]));read.assert_not_called()
 def test_allowed_status_and_cbr_only_reads(self):
  import china_analytic_dialog as d
  with d.reading():
   self.assertTrue(d.allowed_read('GET','https://www.cbr.ru/scripts/XML_daily.asp'))
   self.assertTrue(d.allowed_read('POST','https://marketplace-api.wildberries.ru/api/v3/orders/status',{'orders':[1]}))
   self.assertFalse(d.allowed_read('PATCH','https://marketplace-api.wildberries.ru/api/v3/orders/status',{'orders':[1]}))
   self.assertFalse(d.allowed_read('POST','https://marketplace-api.wildberries.ru/api/v3/orders/status',{'orders':[1],'status':'cancel'}))
 def test_same_job_collection_checkpoint_never_repoll(self):
  w=W();key=p.ROOT+'inputs:'+str(DAY)+':job:901';w.mem[key]=dict(status='partial',cabinet='token_3')
  # Imports are mocked; any attempted API request would fail the test.
  fakecloud=types.SimpleNamespace(Cache=lambda:None,WB=lambda:None,validate_identity=lambda *a:(_ for _ in ()).throw(AssertionError('Repeated identity')))
  with patch.dict(sys.modules,{'requests':types.SimpleNamespace(),'china_cloud_cost_control':fakecloud,'china_moysklad_read':types.SimpleNamespace(read_stock=lambda a:None)}):
   state,returned=p.collect(w,{'id':901},DAY)
  self.assertEqual(key,returned);self.assertEqual(state['status'],'partial')
 def test_full_fresh_collector_reads_only_and_filters_bad_unordered_price(self):
  w=W();calls=[];f=fixture();raworder=f['inputs']['orders']['rows'][0]
  class Response:
   ok=True
   def __init__(self,value):self.value=value
   def json(self):return copy.deepcopy(self.value)
  def get(url,**kw):
   calls.append(('GET',url,kw))
   if url.endswith('/api/v3/orders'):return Response(dict(orders=[raworder],next=0))
   if url.endswith('/list/goods/filter'):return Response(dict(data=dict(listGoods=[dict(nmID=999,vendorCode='other',currencyIsoCode4217='CNY',sizes=[dict(discountedPrice=0)]),dict(nmID=143,vendorCode='143-Bag-black',currencyIsoCode4217='CNY',sizes=[dict(discountedPrice=100)])])))
   if url.endswith('/config'):return Response(dict(currency='CNY'))
   if url.endswith('/count'):return Response(dict(adverts=[dict(advert_list=[dict(advertId=4),dict(advertId=9)])]))
   if url.endswith('/fullstats'):return Response(f['inputs']['advertising']['rows'])
   raise AssertionError(url)
  def post(url,**kw):
   calls.append(('POST',url,kw));self.assertTrue(url.endswith('/api/v3/orders/status'));self.assertEqual(kw['json'],{'orders':[1]})
   return Response(dict(orders=f['inputs']['statuses']['rows']))
  class Analyst:
   def __init__(self,*args):pass
   def collect(self,topic,ids,first,last):
    selfargs=(topic,ids,first,last)
    if selfargs!=('products',[],date(2026,10,1),date(2026,10,30)):raise AssertionError(selfargs)
    return f['inputs']['own_products']
  cloud=types.SimpleNamespace(Cache=lambda:None,WB=lambda:None,validate_identity=lambda *a:None)
  saved=types.SimpleNamespace(saved_products=lambda *a:None)
  reports=types.SimpleNamespace(Reports=lambda w:types.SimpleNamespace(finance=lambda *a:dict(cabinet='token_3',period_from=str(DAY),period_to=str(DAY),rows=[],complete=False)))
  with patch.dict(sys.modules,{'requests':types.SimpleNamespace(get=get,post=post),'china_cloud_cost_control':cloud,'china_moysklad_read':types.SimpleNamespace(read_stock=lambda a:f['inputs']['stock']),'china_saved_products':saved,'china_wb_evidence':reports}),patch('china_analytic_dialog.Analyst',Analyst),patch('china_intraday_analysis.rate',return_value=f['inputs']['fx']),patch.object(p,'now',return_value=CLOCK),patch.dict('os.environ',{'WB_TOKEN_3':'synthetic'}):
   state,key=p.collect(w,{'id':902},DAY)
  self.assertEqual(state['status'],'complete');self.assertEqual(len(state['inputs']['prices']['rows']),1)
  self.assertEqual(calc(state)['totals']['forecast_profit_cny'],18.5)
  self.assertEqual({method for method,_,_ in calls},{'GET','POST'})

if __name__=='__main__':unittest.main()

