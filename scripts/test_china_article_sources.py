import sys,types,unittest,copy,os
from unittest.mock import patch
import china_analytic_dialog as a
from china_article_diagnostic_read import read_current
from test_china_article_diagnostic_read import worker,analyst,inputs,view
from test_china_article_diagnostic import NOW
class ReadPlanTests(unittest.TestCase):
 def test_real_read_plan_is_scoped_and_never_mutates(self):
  w=worker();an=analyst(w);data=inputs();calls=[]
  def live(topic,ids,*x):
   calls.append(('live',topic,ids))
   return dict(rows=data['stock'] if topic=='stock' else data['prices'],observed_at=NOW.isoformat())
  an.live=live
  def http(io,path,method='GET',body=None):
   self.assertEqual(method,'GET');self.assertIsNone(body);calls.append(('http',path))
   if path=='/api/advert/v1/config':return dict(currency='CNY',cpcStep=1,cpcMaxBid=500)
   if path.startswith('/adv/v3/fullstats?'):
    self.assertIn('ids=40000001',path);self.assertIn('endDate=2026-10-28',path)
    return list(data['stats'].values())
   if path=='/adv/v1/budget?id=40000001':return dict(total=100)
   raise AssertionError('Unplanned endpoint '+path)
  def minimums(self,cid,ids,zone):
   calls.append(('minimums',cid,ids,zone));return {n:28 for n in ids}
  class Reports:
   def __init__(self,w):pass
   def funnel(self,first,last):return dict(complete=True,source='WB exact funnel',observed_at=NOW.isoformat(),rows=[dict(nm_id=100,selected=dict(orders=2,clicks=20))])
  modules={'china_price_apply':types.SimpleNamespace(IO=lambda:object()),'china_cloud_cost_control':types.SimpleNamespace(WB=type('WB',(),{'minimums':minimums})),'china_loss_ads':types.SimpleNamespace(http=http,current=lambda io,ids:data['campaigns']),'china_wb_evidence':types.SimpleNamespace(Reports=Reports)}
  with patch.dict(sys.modules,modules):result=read_current(an,[100],view(),'2026-10-25','2026-10-27')
  self.assertEqual(result['general'][100]['orders'],2);self.assertEqual(result['budgets']['40000001'],100);self.assertEqual(result['minimums']['40000001:100:recommendations'],28);self.assertFalse(result['gaps'])
  self.assertTrue(any(c[0]=='minimums' and c[2]==[100] for c in calls))
 def test_get_public_offer_does_not_allow_other_public_or_marketplace_endpoints(self):
  # The core read fence must reject cart and price mutations.
  with patch.dict(sys.modules,{'china_wb_evidence':types.SimpleNamespace(allowed_read=lambda *x:False)}),a.reading():
   self.assertTrue(a.allowed_read('GET','https://www.wildberries.ru/catalog/100/detail.aspx'))
   self.assertFalse(a.allowed_read('POST','https://www.wildberries.ru/catalog/100/detail.aspx'))
   self.assertFalse(a.allowed_read('GET','https://www.wildberries.ru/lk/basket'))
   self.assertFalse(a.allowed_read('PATCH','https://advert-api.wildberries.ru/api/advert/v1/bids'))
 def test_real_stock_reader_requires_all_modes_gzip_and_complete_pages(self):
  w=worker();an=analyst(w)
  class R:
   ok=True
   def __init__(self,p):self.p=p
   def json(self):return self.p
  def get(url,params,headers,timeout):
   self.assertEqual(headers['Accept-Encoding'],'gzip')
   if url.endswith('/entity/store'):return R(dict(meta=dict(size=1),rows=[dict(name='МСК',meta=dict(href='store'),archived=False)]))
   self.assertEqual(params['filter'],'store=store;stockMode=all;quantityMode=all')
   return R(dict(meta=dict(size=1),rows=[dict(article='test-bag',stock=5,reserve=2,price=60000)]))
  with patch.dict(os.environ,{'MOYSKLAD_API_TOKEN':'synthetic'}),patch.dict(sys.modules,{'requests':types.SimpleNamespace(get=get)}):
   result=an.collect('stock',[100],None,None)
  self.assertEqual(result['rows'][0]['available'],3);self.assertEqual(result['rows'][0]['cost_rub'],600)
 def test_stock_page_without_total_is_not_complete(self):
  w=worker();an=analyst(w)
  class R:
   ok=True
   def json(self):return dict(rows=[dict(name='МСК',meta=dict(href='store'))])
  with patch.dict(os.environ,{'MOYSKLAD_API_TOKEN':'synthetic'}),patch.dict(sys.modules,{'requests':types.SimpleNamespace(get=lambda *a,**k:R())}):
   with self.assertRaisesRegex(ValueError,'неполон'):an.collect('stock',[100],None,None)
if __name__=='__main__':unittest.main()
