import unittest,os,json,base64,sys,types
from unittest.mock import patch
from datetime import datetime,timezone
from china_wb_evidence import *

def row(rid=1,op='销售',doc='销售',nm=10,**kw):
 r=dict(rrdId=rid,nmId=nm,currency='cny',sellerOperName=op,docTypeName=doc,rrDate='2026-10-21',createDate='2026-10-23',quantity=1,forPay='80',retailPriceWithDisc='100',deliveryService='0',rebillLogisticCost='0',paidStorage='0',paidAcceptance='0',penalty='0',deduction='0',additionalPayment='0')
 return dict(r,**kw)
def state(*rows):return dict(rows=list(rows),complete=True,source_keys=['private-source'])
class Worker:
 def __init__(self):self.values={}
 def get(self,k):return self.values.get(k)
 def save(self,k,v):self.values[k]=v
 def db(self,*a,**kw):return [{'claimed':True}]
class Response:
 def __init__(self,code,data):self.status_code=code;self.data=data;self.headers={}
 def json(self):return self.data
def token():return 'a.'+base64.urlsafe_b64encode(json.dumps(dict(sid='synthetic-seller',acc=3)).encode()).decode().rstrip('=')+'.z'
class Tests(unittest.TestCase):
 def test_money_missing_and_nonfinite(self):
  for n in [None,True,'NaN','Infinity']:
   with self.assertRaises(ValueError):money(n)
 def test_returns_signed_and_commission_not_doubled(self):
  r=settlement(state(row(),row(2,op='退货',doc='退货',forPay='20')), '2026-10-21','2026-10-21',costs={10:120})
  self.assertEqual(r['wb_cash_cny'],60);self.assertEqual(r['accounted_contribution_rub'],720);self.assertFalse(r['commission_subtracted_again']);self.assertIsNone(r['net_profit_rub'])
 def test_ad_deduction_not_subtracted_twice(self):
  r=settlement(state(row(),row(2,op='扣款',doc='',nm=0,forPay='0',deduction='10',bonusTypeName='Provision of «WB Promotion» services')),'2026-10-21','2026-10-21',costs={10:120})
  self.assertEqual(r['wb_cash_cny'],70);self.assertEqual(r['wb_promotion_included_cny'],10);self.assertFalse(r['ad_spend_subtracted_again'])
 def test_missing_cogs_not_zero(self):
  r=settlement(state(row()),'2026-10-21','2026-10-21');self.assertIsNone(r['accounted_contribution_rub'])
 def test_mixed_currencies_fail(self):
  with self.assertRaises(ValueError):settlement(state(row(currency='RUB'),row(2)),'2026-10-21','2026-10-21')
 def test_duplicate_operation_fail(self):
  with self.assertRaises(ValueError):settlement(state(row(),row()),'2026-10-21','2026-10-21')
 def test_published_not_closed_profit(self):
  r=settlement(state(row()),'2026-10-21','2026-10-21',costs={10:120});self.assertFalse(r['is_closed_order_cohort']);self.assertEqual(r['publication_latest'],'2026-10-23');self.assertIsNone(r['net_profit_rub'])
 def test_missing_expense_field(self):
  r=row();r.pop('deliveryService');v=settlement(state(r),'2026-10-21','2026-10-21',costs={10:120});self.assertIsNone(v['accounted_contribution_rub'])
 def test_unknown_operation_not_profit(self):
  r=settlement(state(row(op='correction')),'2026-10-21','2026-10-21');self.assertTrue(any('Unclassified' in m for m in r['missing']))
 def test_no_rows_not_zero(self):
  r=settlement(state(),'2026-10-21','2026-10-21');self.assertIsNone(r['wb_cash_cny']);self.assertIsNone(r['net_profit_rub'])
 def test_sku_shared_not_silently_allocated(self):
  r=settlement(state(row()),'2026-10-21','2026-10-21',[10],{10:120});self.assertTrue(any('shared' in m for m in r['missing']))
 def test_owner_tax5_and_own_cogs_calculated(self):
  r=settlement(state(row()),'2026-10-21','2026-10-21',costs={10:120})
  self.assertEqual(r['parts_cny']['tax'],5);self.assertEqual(r['parts_cny']['cogs'],10);self.assertEqual(r['calculated_profit_rub'],780)
 def test_historical_positive_stock_cost_when_current_missing(self):
  w=Worker();w.catalog=lambda:[('10','synthetic')]
  href='https://api.moysklad.ru/api/remap/1.2/entity/product/synthetic-id'
  raw={'rows':[{'id':'own-product','meta':{'href':href},'article':'synthetic','buyPrice':{'value':999999,'currency':{'isoCode':'RUB'}}}]};calls=[]
  def get(url,**kw):
   calls.append(kw.get('params',{}))
   data=raw if url.endswith('/product') else {'rows':[{'name':'МСК','meta':{'href':'https://api.moysklad.ru/api/remap/1.2/entity/store/synthetic'}}]} if url.endswith('/store') else {'meta':{'size':1},'rows':[{'article':'synthetic','meta':{'href':href},'stock':2,'price':24000}]}
   return types.SimpleNamespace(ok=True,json=lambda:data)
  transport=types.SimpleNamespace(get=get)
  with patch.dict(sys.modules,{'requests':transport}),patch.dict(os.environ,{'MOYSKLAD_API_TOKEN':'synthetic'}):
   costs,evidence=own_costs(w,{'rows':[]},[row()],'2026-10-21','2026-10-21')
  self.assertEqual(costs[10],240);self.assertEqual(evidence[0]['basis'],'Historical positive-stock average');self.assertIn('moment=2026-10-20 23:59:59',calls[-1]['filter'])
 def test_ambiguous_moysklad_product_not_guessed(self):
  w=Worker();w.catalog=lambda:[('10','synthetic')]
  raw={'rows':[{'article':'synthetic'},{'article':'synthetic'}]}
  transport=types.SimpleNamespace(get=lambda *a,**kw:types.SimpleNamespace(ok=True,json=lambda:raw))
  with patch.dict(sys.modules,{'requests':transport}),patch.dict(os.environ,{'MOYSKLAD_API_TOKEN':'synthetic'}):
   costs,_=own_costs(w,{'rows':[]},[row()],'2026-10-21','2026-10-21')
  self.assertIsNone(costs[10])
 def test_short_page_needs_204_and_cursor(self):
  w=Worker();responses=iter([Response(200,[row()]),Response(204,[])]);calls=[]
  def send(url,**kw):calls.append(kw['json']);return next(responses)
  with patch.dict(os.environ,{'WB_TOKEN_3':token(),'WB_FINANCE_TOKEN_3':token()}):
   r=Reports(w,send);a=r.finance('2026-10-21','2026-10-22');self.assertFalse(a['complete']);self.assertEqual(a['rrd_id'],1)
   w.values[ROOT+'rate:finance']={};b=r.finance('2026-10-21','2026-10-22');self.assertTrue(b['complete']);self.assertEqual(calls[1]['rrdId'],1)
 def test_wrong_finance_seller_blocked(self):
  with patch.dict(os.environ,{'WB_TOKEN_3':token(),'WB_FINANCE_TOKEN_3':'invalid'}):
   with self.assertRaises(ValueError):Reports(Worker()).request(FINANCE,dict(dateFrom='x',dateTo='x',rrdId=0,period='daily'))
 def test_no_mutations_allowed(self):
  self.assertFalse(allowed_read('PATCH',FUNNEL,{}));self.assertFalse(allowed_read('POST','https://advert-api.wildberries.ru/adv/v1/budget',{}))
 def test_funnel_clicks_never_impressions(self):
  p={'start':'2026-10-22','end':'2026-10-22'};past={'start':'2026-10-21','end':'2026-10-21'}
  s=dict(period=p,openCount=100,cartCount=3,orderCount=2,orderSum=30,buyoutCount=1,cancelCount=0)
  rows=normalize_funnel([dict(product={'nmId':10,'vendorCode':'synthetic'},statistic={'selected':s,'past':dict(s,period=past)})],p,past,'source')
  self.assertEqual(rows[0]['selected']['clicks'],100);self.assertIsNone(rows[0]['selected']['total_impressions']);self.assertEqual(rows[0]['selected']['click_order_pct'],2)
if __name__=='__main__':unittest.main()

