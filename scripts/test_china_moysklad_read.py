import copy,unittest
import china_moysklad_read as m
A='00000000-0000-0000-0000-000000000001';B='00000000-0000-0000-0000-000000000002'
def page(rows):return {'meta':{'size':len(rows)},'rows':rows}
STORE={'id':A,'name':'МСК','meta':{'href':m.BASE+'/entity/store/'+A}}
PRODUCT={'article':'SKU-A','meta':{'href':m.BASE+'/entity/product/'+B}}
class Response:
 def __init__(self,data,code=200):self.data=data;self.status_code=code
 def json(self):return copy.deepcopy(self.data)
class ReadTests(unittest.TestCase):
 def reader(self,report=None,products=None,stores=None):
  calls=[]
  def get(url,**kw):
   calls.append((url,kw));self.assertFalse(kw['allow_redirects']);self.assertEqual(kw['params']['limit'],100)
   if url.endswith('/entity/store'):return Response(page(stores if stores is not None else [STORE]))
   if url.endswith('/entity/product'):return Response(page(products if products is not None else [PRODUCT]))
   self.assertIn(';product='+PRODUCT['meta']['href'],kw['params']['filter'])
   return Response(page(report if report is not None else [dict(PRODUCT,stock=10,reserve=3,price=1200)]))
  return m.Reader(token='not-a-real-token',get=get,sleep=lambda _:None),calls
 def test_exact_stock_reserve_and_cost(self):
  r,c=self.reader();v=r.stock(['SKU-A']);self.assertEqual(v['rows'][0]['stock']-v['rows'][0]['reserve'],7);self.assertEqual(v['rows'][0]['price'],1200);self.assertTrue(v['coverage_complete']);self.assertEqual(len(c),3)
 def test_missing_row_not_zero(self):
  r,_=self.reader(report=[]);v=r.stock(['SKU-A']);self.assertEqual(v['rows'],[]);self.assertEqual(v['missing_articles'][0]['reason'],'report_row_missing');self.assertFalse(v['coverage_complete'])
 def test_zero_is_preserved(self):
  r,_=self.reader(report=[dict(PRODUCT,stock=0,reserve=0,price=None)]);row=r.stock(['SKU-A'])['rows'][0];self.assertEqual(row['stock'],0);self.assertIsNone(row['price'])
 def test_ambiguous_product_not_selected(self):
  r,c=self.reader(products=[PRODUCT,PRODUCT]);v=r.stock(['SKU-A']);self.assertEqual(len(c),2);self.assertEqual(v['missing_articles'][0]['reason'],'product_ambiguous')
 def test_warehouse_ambiguity_fails(self):
  r,_=self.reader(stores=[STORE,STORE])
  with self.assertRaises(m.MoySkladReadError):r.stock(['SKU-A'])
 def test_foreign_product_response_fails(self):
  r,_=self.reader(report=[dict(PRODUCT,meta={'href':m.BASE+'/entity/product/'+A})])
  with self.assertRaises(m.MoySkladReadError):r.stock(['SKU-A'])
 def test_foreign_warehouse_url_fails(self):
  r,_=self.reader(stores=[dict(STORE,meta={'href':'https://example.com/'+A})])
  with self.assertRaises(m.MoySkladReadError):r.stock(['SKU-A'])
 def test_duplicate_or_filter_injection_rejected(self):
  r,_=self.reader()
  for a in [['SKU-A','sku-a'],['SKU-A;store=bad'],[]]:
   with self.assertRaises(m.MoySkladReadError):r.stock(a)
 def test_transient_only_retries(self):
  seq=[Response({},504),Response(page([]))];sleeps=[]
  r=m.Reader(token='secret',get=lambda *a,**k:seq.pop(0),sleep=sleeps.append);self.assertEqual(r.pages('/entity/store',{}),[]);self.assertEqual(sleeps,[2])
 def test_auth_failure_not_retried(self):
  calls=[]
  r=m.Reader(token='secret',get=lambda *a,**k:(calls.append(1) or Response({},401)),sleep=lambda _:None)
  with self.assertRaisesRegex(m.MoySkladReadError,'HTTP 401'):r.pages('/entity/store',{})
  self.assertEqual(calls,[1])
 def test_connections_bounded_and_sanitized(self):
  calls=[]
  def fail(*a,**k):calls.append(1);raise m.requests.exceptions.ConnectionError('secret credentials')
  r=m.Reader(token='secret',get=fail,sleep=lambda _:None)
  with self.assertRaisesRegex(m.MoySkladReadError,'after 3 attempts') as ex:r.pages('/entity/store',{})
  self.assertNotIn('secret',str(ex.exception));self.assertEqual(len(calls),3)
 def test_truncated_page_fails(self):
  r=m.Reader(token='x',get=lambda *a,**k:Response({'meta':{'size':1},'rows':[]}),sleep=lambda _:None)
  with self.assertRaises(m.MoySkladReadError):r.pages('/entity/store',{})
 def test_no_write_endpoint(self):
  r,_=self.reader()
  with self.assertRaises(m.MoySkladReadError):r.get('/entity/demand',{})
if __name__=='__main__':unittest.main()
