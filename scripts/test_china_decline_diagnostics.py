import types,sys,unittest
from datetime import datetime,timezone
from unittest.mock import patch
from china_decline_diagnostics import selected,ad_rows,collect

class DiagnosticsTests(unittest.TestCase):
 def test_ad_apps_summed_without_campaign_total_double_count(self):
  rows=[dict(level='SKU_app',nm_id=10,date='2026-10-22',sum=2,sum_price=100,orders=1,clicks=3,views=20),dict(level='SKU_app',nm_id=10,date='2026-10-22',sum=3,sum_price=100,orders=1,clicks=4,views=30),dict(level='campaign_total',date='2026-10-22',sum=5)]
  value=ad_rows(rows,[10])[(10,'2026-10-22')];self.assertEqual(value['spend'],5);self.assertEqual(value['drr_pct'],2.5);self.assertEqual(value['clicks'],7)
 def test_each_day_and_minimum_are_actually_requested(self):
  class W:
   now=datetime(2026,10,23,18,tzinfo=timezone.utc)
   def catalog(self):return [('10','bag')]
  calls=[]
  class A:
   w=W()
   def live(self,topic,ids,first,last):
    calls.append((topic,first,last));meta=dict(source=topic,observed_at='2026-10-23T18:00:00Z')
    if topic=='orders':return dict(meta,top_yesterday_declines=[dict(nm_id=10,article='bag',daily={'2026-10-21':5,'2026-10-22':2,'2026-10-23':1},delta_yesterday=-3,delta_today_matched_clock=-1)],top_today_declines=[])
    if topic=='products':return dict(meta,rows=[dict(nm_id=10,open_card_count=100,funnel_orders_count=2,sparkline_prices=[100])])
    if topic=='stock':return dict(meta,rows=[dict(article='bag',available=20)])
    if topic=='prices':return dict(meta,rows=[dict(nm_id=10,seller_price=100)])
    return dict(meta,rows=[],campaigns=[dict(id=1,status=9,currency='CNY',bid_type='manual',settings=dict(payment_type='cpc'),nm_settings=[dict(nm_id=10,bids_kopecks=dict(recommendations=40))])])
  modules={}
  m=types.ModuleType('china_price_apply');m.IO=lambda:object();modules['china_price_apply']=m
  m=types.ModuleType('china_loss_ads');m.http=lambda *a:dict(cpcStep=1);modules['china_loss_ads']=m
  m=types.ModuleType('china_ad_rule');m.minimums=lambda *a:{10:28};modules['china_ad_rule']=m
  with patch.dict(sys.modules,modules),patch('china_experience.decision_context',return_value=dict(experiences=[])):
   result=collect(A())
  self.assertEqual([x for x in calls if x[0]=='products'],[('products',d,d) for d in ['2026-10-21','2026-10-22','2026-10-23']])
  self.assertEqual(result['rows'][0]['active_campaigns'][0]['minimum_minor'],28);self.assertEqual(result['wb_writes'],0)
  self.assertEqual(result['rows'][0]['funnel_daily'][0]['customer_daily_price'],100)

if __name__=='__main__':unittest.main()

