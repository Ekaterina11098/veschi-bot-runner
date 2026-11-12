import unittest,copy,types,sys
from unittest.mock import patch
import china_advertising_v2 as m

class ScopedStatistics(unittest.TestCase):
 def run_case(self,response):
  source={'status':'complete','period_from':'2026-11-05','period_to':'2026-11-11','batches':{'0':{'campaigns':{'adverts':[{'id':41756218,'status':9,'timestamps':{'created':'2026-11-10T15:00:00+03:00'}}]},'stats':[]}}}
  class IO:
   def __init__(self):self.data={m.FORMAT:{'status':'approved','version':m.VERSION},'china_agent:advertising_source:2026-11-12:v2':copy.deepcopy(source)}
   def get(self,k):return self.data.get(k)
   def create(self,k,v):self.data[k]=copy.deepcopy(v);return True
   def put(self,k,v):self.data[k]=copy.deepcopy(v)
  io=IO()
  with patch.object(m,'http',return_value=response) as http,patch.object(m.time,'sleep'),patch.object(m,'collect_alternative_zero_statistics',return_value={}),patch.dict(sys.modules,{'china_morning_readiness':types.SimpleNamespace(ensure=lambda *a:None)}):
   result=m.collect(io,'2026-11-12')
  self.assertIn('beginDate=2026-11-10',http.call_args.args[1]);return result
 def test_null_is_unknown_not_zero(self):self.assertEqual(self.run_case(None)['batches']['0']['stats'],[])
 def test_exact_statistics_retained(self):
  rows=[{'advertId':41756218,'sum':2,'days':[]}]
  self.assertEqual(self.run_case(rows)['batches']['0']['stats'],rows)
 def test_wrong_campaign_rejected(self):
  with self.assertRaises(ValueError):self.run_case([{'advertId':1}])
 def alternate(self,positive=False,wrong_cabinet=False):
  fields=('ac_spending_sum','ac_orders_sum','ac_orders','ac_clicks','ac_views','ac_add_to_cart')
  rows=[dict(date=d,**{f:0 for f in fields})for d in ('2026-11-09','2026-11-10','2026-11-11')]
  if positive:rows[-1]['ac_spending_sum']=2
  def call(method,params):
   name=params['name']
   if name=='wbbidder_cabinets':return {'data':[{'id':939742,'name':'wrong' if wrong_cabinet else 'VESCHI Гонконг','info':{'currency':'CNY'}}]}
   if name=='wbbidder_campaigns':return {'data':[{'id':123,'wb_id':41756218,'user_token_id':939742}]}
   return {'data':rows}
  def discover(token,**kw):kw['extra_reader'](call,{},set());return {'status':'read_access_checked'}
  class IO:
   def __init__(self):self.data={}
   def get(self,k):return self.data.get(k)
   def create(self,k,v):self.data[k]=v;return True
   def put(self,k,v):self.data[k]=v
  with patch.dict(sys.modules,{'analytics.mpstats_probe':types.SimpleNamespace(discover=discover,unpack_tool=lambda v:v)}):
   return m.collect_alternative_zero_statistics(IO(),{'id':41756218,'settings':{'name':'test'}},'2026-11-12')
 def test_alternative_explicit_zero_days_accepted_without_sku_claim(self):
  result=self.alternate();self.assertEqual(len(result['days']),3);self.assertFalse(result['sku_statistics_available']);self.assertFalse(result['recommendations_allowed'])
 def test_positive_alternative_money_not_imported_without_unit_reconciliation(self):self.assertEqual(self.alternate(positive=True),{})
 def test_wrong_alternative_cabinet_rejected(self):self.assertEqual(self.alternate(wrong_cabinet=True),{})

if __name__=='__main__':unittest.main()
