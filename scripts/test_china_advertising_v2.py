import copy,unittest,sys,types
from datetime import datetime,timezone
from unittest.mock import patch
from china_advertising_v2 import recommend,build,ratio,sums,history,http
from china_advertising_v2_png import render
from china_daily_ad_actions import plan,bind,handle,BIND
from china_advertising_delivery import deliver,CHAT

def row(spend,amount,orders=1):return dict(spend=spend,amount=amount,orders=orders if amount else 0,views=100,clicks=10)
def campaign():return dict(id=12,status=9,currency='CNY',bid_type='manual',settings=dict(name='Сумки',payment_type='cpc',placements=dict(search=False,recommendations=True)),nm_settings=[dict(nm_id=1,bids_kopecks=dict(recommendations=40,search=0)),dict(nm_id=2,bids_kopecks=dict(recommendations=28,search=0))],restrictions=dict(can_change_nms=True),timestamps=dict(created='2026-10-01T00:00:00+03:00'))
class Fake:
 def __init__(self):self.data={};self.now=datetime.now(timezone.utc)
 def get(self,k):return copy.deepcopy(self.data.get(k))
 def put(self,k,v):self.data[k]=copy.deepcopy(v)
 def create(self,k,v):
  if k in self.data:return False
  self.put(k,v);return True
 def save(self,k,v,insert=False):return self.create(k,v) if insert else self.put(k,v)
class DailyFormatTests(unittest.TestCase):
 days=['2026-10-23','2026-10-24','2026-10-25']
 def recommendation(self,values,changes=(),minimum=28,price=100):return recommend(campaign(),campaign()['nm_settings'][0],dict(zip(self.days,values)),self.days,list(changes),minimum,price)
 def test_ratio_of_sums_includes_zero_order_expense(self):self.assertAlmostEqual(ratio(sums([row(10,100),row(20,0),row(1,1000)])),31/1100*100)
 def test_single_anomaly_does_not_exclude(self):
  r=self.recommendation([row(2,100),row(1,100),row(11,100)]);self.assertIsNone(r['action']);self.assertIn('Единичное',r['reason'])
 def test_rising_drr_below_period5_reduces(self):
  r=self.recommendation([row(.98,100),row(3.47,100),row(9.66,100)]);self.assertEqual(r['action']['target_minor'],32)
 def test_no_full_day_after_change_is_not_repeated(self):
  changes=[dict(cid=12,nm=1,kind='bid',at='2026-10-25T10:00:00+03:00')];r=self.recommendation([row(20,100)]*3,changes);self.assertIsNone(r['action']);self.assertIn('26.10',r['decision'])
 def test_improving_post_change_above5_keeps_test(self):
  c=campaign();ds={'2026-10-21':row(20,100),'2026-10-22':row(20,100),'2026-10-23':row(40,100),'2026-10-24':row(10,100),'2026-10-25':row(10,100)}
  r=recommend(c,c['nm_settings'][0],ds,self.days,[dict(cid=12,nm=1,kind='bid',at='2026-10-23T10:00:00+03:00')],28,100);self.assertIsNone(r['action']);self.assertIn('50%',r['reason'])
 def test_no_order_spend_recommends_exact_exclusion(self):
  r=self.recommendation([row(2,0)]*3);self.assertEqual(r['action']['kind'],'ad_exclude_sku');self.assertEqual(r['action']['campaign_id'],12)
 def test_unknown_price_not_zero_or_imagined_threshold(self):self.assertIsNone(self.recommendation([row(2,0)]*3,price=None))
 def test_price_change_gets_its_own_full_day(self):
  r=self.recommendation([row(20,100)]*3,[dict(cid=12,nm=1,kind='price',at='2026-10-25T10:00:00+03:00')]);self.assertIsNone(r['action'])
 def test_read_only_transport_denies_budget_write(self):
  with patch.dict(sys.modules,{'requests':types.ModuleType('requests')}):
   with self.assertRaises(ValueError):http(None,'/adv/v1/budget/deposit?id=12','POST',{'sum':100})
 def test_verified_history_only(self):
  before=campaign();after=copy.deepcopy(before);after['nm_settings']=after['nm_settings'][1:]
  records=[dict(payload=dict(status='verified',before=before,after=after,verified_at='2026-10-25T10:00:00+03:00'))]
  self.assertEqual(history(records)[0]['kind'],'excluded');records[0]['payload']['status']='uncertain';self.assertEqual(history(records),[])
 def test_binding_contains_only_actions_of_that_page(self):
  io=Fake();p=plan(io,'2026-10-26',dict(family='drr',actions=[dict(id='12:1',kind='ad_exclude_sku')]),0);other=plan(io,'2026-10-26',dict(family='budgets',actions=[]),1)
  f=dict(plan_id=p['plan_id'],plan_sha256=p['plan_sha256']);bind(io,f,dict(message_id=123));b=io.get(BIND+'123');self.assertEqual(b['plan_id'],p['plan_id']);self.assertNotEqual(b['plan_id'],other['plan_id'])
 def test_multipart_delivery_preserves_cursor(self):
  io=Fake();files=[dict(kind='drr:001',bytes=b'a'),dict(kind='drr:002',bytes=b'b'),dict(kind='budgets:001',bytes=b'c')];calls=[]
  def send(f):
   calls.append(f['kind'])
   if f['kind']=='drr:002':raise TimeoutError()
   return dict(chat=dict(id=CHAT),message_id=111)
  with self.assertRaises(RuntimeError):deliver(io,'2026-10-26',files,send)
  with self.assertRaises(RuntimeError):deliver(io,'2026-10-26',files,send)
  self.assertEqual(calls,['drr:001','drr:002'])
 def test_multipart_foreign_kind_rejected(self):
  with self.assertRaises(ValueError):deliver(Fake(),'2026-10-26',[dict(kind='other:001',bytes=b'a')],lambda _:None)
if __name__=='__main__':unittest.main()

