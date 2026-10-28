import unittest,copy
from datetime import datetime,timezone,timedelta
from china_zero_orders_stock import attach
class T(unittest.TestCase):
 def base(self):return dict(zero=[dict(article=x,orders=0) for x in ['a','b','c','d']],unknown=[dict(article='e',orders=None)])
 def source(self):return dict(complete=True,observed_at=datetime.now(timezone.utc).isoformat(),rows=[dict(article='a',stock=10,reserve=2),dict(article='b',stock=0,reserve=0),dict(article='c',stock=4,reserve=4)])
 def test_split(self):
  p=attach(self.base(),self.source());self.assertEqual(p['stock_counts'],dict(available=1,empty=1,reserved=1,unknown=1));self.assertEqual(p['zero'][0]['moysklad']['available'],8);self.assertEqual(len(p['unknown']),1)
 def test_missing_reserve_unknown(self):
  s=self.source();s['rows'][0].pop('reserve');self.assertEqual(attach(self.base(),s)['zero'][0]['moysklad']['group'],'unknown')
 def test_duplicates_unknown(self):
  s=self.source();s['rows'].append(s['rows'][0]);self.assertEqual(attach(self.base(),s)['zero'][0]['moysklad']['group'],'unknown')
 def test_stale_unknown(self):
  s=self.source();s['observed_at']=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat();self.assertEqual(attach(self.base(),s)['stock_counts']['unknown'],4)
 def test_partial_unknown(self):
  s=self.source();s['complete']=False;self.assertEqual(attach(self.base(),s)['stock_counts']['unknown'],4)

class StockTransportTests(unittest.TestCase):
 def test_collect_requests_exact_gzip_header(self):
  import os,sys
  from types import SimpleNamespace
  from unittest.mock import patch
  from china_zero_orders_stock import collect_stock
  class W:
   def get(self,k):return None
   def save(self,k,p):self.saved=p
  class R:
   ok=True
   def __init__(self,p):self.p=p
   def json(self):return self.p
  calls=[]
  def get(url,params,headers,timeout):
   calls.append((url,params))
   if headers.get('Accept-Encoding')!='gzip':raise ValueError('MoySklad HTTP 406')
   if url.endswith('/entity/store'):return R(dict(meta=dict(size=1),rows=[dict(name='МСК',id='warehouse',meta=dict(href='store-url'))]))
   return R(dict(meta=dict(size=1),rows=[dict(article='test',stock=2,reserve=1)]))
  with patch.dict(os.environ,{'MOYSKLAD_API_TOKEN':'synthetic'}),patch.dict(sys.modules,{'requests':SimpleNamespace(get=get)}):
   result=collect_stock(W())
  self.assertTrue(result['complete']);self.assertEqual(len(calls),2)
  self.assertIn('stockMode=all;quantityMode=all',calls[1][1]['filter'])
 def test_stock_failure_preserves_confirmed_zero_orders_as_unknown_stock(self):
  from unittest.mock import patch
  from china_zero_orders_stock import enrich
  report=dict(zero=[dict(article='test',orders=0)],unknown=[],zero_count=1,unknown_count=0)
  with patch('china_zero_orders_stock.collect_stock',side_effect=ValueError('HTTP 406')):
   result=enrich(None,report)
  self.assertEqual(result['zero_count'],1);self.assertEqual(result['zero'][0]['orders'],0)
  self.assertEqual(result['stock_counts']['unknown'],1);self.assertIsNone(result['zero'][0]['moysklad']['available'])
if __name__=='__main__':unittest.main()


