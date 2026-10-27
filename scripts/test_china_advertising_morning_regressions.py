import copy,io,unittest
from datetime import datetime
from unittest.mock import patch
from PIL import ImageDraw
from china_advertising_v2 import history,recommend
# Offline fixture only: production Actions installs requests; these tests never use HTTP.
try:
 import requests
except ModuleNotFoundError:
 import sys,types
 sys.modules['requests']=types.SimpleNamespace(Timeout=TimeoutError,ConnectionError=ConnectionError)
from china_advertising_state import AdvertisingIO
from china_advertising_v2_png import render,GREEN,RED,INK
from test_china_advertising_v2 import campaign,row

class CompleteDayRegressionTests(unittest.TestCase):
 def test_owner_addition_day_cannot_generate_exclusion(self):
  c=campaign();after=copy.deepcopy(c);before=copy.deepcopy(c);before['nm_settings']=before['nm_settings'][1:]
  events=history([dict(payload=dict(status='verified',before=before,after=after,verified_at='2026-10-26T13:22:25Z'))])
  days=['2026-10-24','2026-10-25','2026-10-26'];ds=dict(zip(days,[row(0,0),row(0,0),row(32.48,0)]))
  self.assertIsNone(recommend(c,c['nm_settings'][0],ds,days,events,40,429))
  # On the next morning only the full post-change day may justify the action.
  days=['2026-10-25','2026-10-26','2026-10-27'];ds['2026-10-27']=row(24,0)
  result=recommend(c,c['nm_settings'][0],ds,days,events,40,429)
  self.assertEqual(result['action']['kind'],'ad_exclude_sku')
  self.assertIn('24.00',result['reason'])
  self.assertNotIn('56.48',result['reason'])
 def test_readdition_resets_test_and_uses_moscow_day(self):
  c=campaign()
  changes=[dict(cid=12,nm=1,kind='added',at='2026-10-26T21:05:00Z')]
  days=['2026-10-25','2026-10-26','2026-10-27']
  self.assertIsNone(recommend(c,c['nm_settings'][0],dict.fromkeys(days,row(40,0)),days,changes,40,100))
 def test_mapped_owner_bid_batch_requires_matching_after(self):
  c=campaign();c['nm_settings'][0]['bids_kopecks']['recommendations']=31
  payload=dict(status='verified',verified_at='2026-10-26T18:45:30Z',after={'12':c},items=[dict(cid=12,nm=1,old=28,target=31)])
  events=history([payload]);self.assertEqual(len(events),1);self.assertEqual(events[0]['kind'],'bid')
  days=['2026-10-24','2026-10-25','2026-10-26']
  result=recommend(c,c['nm_settings'][0],dict.fromkeys(days,row(40,0)),days,events,28,100)
  self.assertIsNone(result['action'])
  payload['items'][0]['target']=32;self.assertEqual(history([payload]),[])
 def test_price_receipt_and_applied_item_reset_test(self):
  def price(p):return dict(nmID=1,currencyIsoCode4217='CNY',sizes=[dict(discountedPrice=p)])
  direct=dict(status='verified',completed_at='2026-10-26T16:19:00Z',before=price(408.5),after=price(429))
  batch=dict(status='done',completed_at='2026-10-26T16:30:00Z',items=[dict(status='applied',before=price(408.5),readback=price(429))])
  self.assertEqual(history([direct])[0]['kind'],'price')
  self.assertEqual(history([batch])[0]['kind'],'price')
  batch['items'][0]['status']='uncertain';self.assertEqual(history([batch]),[])
  direct['status']='uncertain';self.assertEqual(history([direct]),[])
 def test_rising_day_drr_does_not_reduce_healthy_three_days(self):
  days=['2026-10-24','2026-10-25','2026-10-26'];c=campaign()
  values=[row(19.57,493),row(21.18,493),row(28.35,493)]
  result=recommend(c,c['nm_settings'][0],dict(zip(days,values)),days,[],28,493)
  self.assertIsNone(result['action'])
 def test_healthy_post_change_period_not_hidden_by_old_losses(self):
  days=['2026-10-24','2026-10-25','2026-10-26'];c=campaign()
  values=[row(40,100),row(1,100),row(2,100)]
  event=dict(cid=12,nm=1,kind='bid',at='2026-10-24T10:00:00+03:00')
  self.assertIsNone(recommend(c,c['nm_settings'][0],dict(zip(days,values)),days,[event],28,100))

class StateRetryTests(unittest.TestCase):
 def test_state500_retries_within_same_run(self):
  io=object.__new__(AdvertisingIO)
  with patch('china_price_apply.IO.db',side_effect=[RuntimeError('State HTTP 500'),[{'ok':True}]]) as request,patch('china_advertising_state.time.sleep'):
   self.assertEqual(io.db('telegram_api_cache?cache_key=eq.a','PATCH',{'payload':1}),[{'ok':True}])
   self.assertEqual(request.call_count,2)
 def test_retries_are_bounded(self):
  io=object.__new__(AdvertisingIO)
  with patch('china_price_apply.IO.db',side_effect=RuntimeError('State HTTP 503')) as request,patch('china_advertising_state.time.sleep'):
   with self.assertRaises(RuntimeError):io.db('telegram_api_cache?cache_key=eq.a')
   self.assertEqual(request.call_count,3)
 def test_non_idempotent_post_and_integrity_error_not_retried(self):
  io=object.__new__(AdvertisingIO)
  for method,prefer,error in [('POST',None,'State HTTP 500'),('PATCH',None,'State readback mismatch')]:
   with patch('china_price_apply.IO.db',side_effect=RuntimeError(error)) as request,patch('china_advertising_state.time.sleep'):
    with self.assertRaises(RuntimeError):io.db('telegram_api_cache',method,{},prefer)
    self.assertEqual(request.call_count,1)

class TotalsColorTests(unittest.TestCase):
 def test_actual_total_text_has_green_red_or_black_fill(self):
  for spend,amount,wanted in [(3,100,GREEN),(6,100,RED),(3,0,INK)]:
   metrics=dict(row(spend,amount))
   c=dict(id=12,name='Test',period=metrics,last=metrics,attention=[],notes=[],member_count=2)
   bundle=dict(days=['2026-10-24','2026-10-25','2026-10-26'],source_observed_at='27.10 07:15',campaigns=[c])
   original=ImageDraw.ImageDraw.text;calls=[]
   def capture(draw,xy,text,*args,**kwargs):
    calls.append((xy,text,kwargs.get('fill')));return original(draw,xy,text,*args,**kwargs)
   with patch.object(ImageDraw.ImageDraw,'text',capture):render(bundle)
   totals=[call for call in calls if call[1].startswith('Общая ДРР')]
   self.assertEqual(len(totals),2)
   for position,_,_ in totals:
    self.assertTrue(any(xy[1]==position[1] and xy[0]>position[0] and fill==wanted for xy,text,fill in calls))



class DeliverySlotTests(unittest.TestCase):
 def test_preparation_freezes_once_then_0730_delivers_without_recollection(self):
  import os
  import china_advertising_daily as daily
  from test_china_advertising_v2 import Fake
  cache=Fake()
  class Clock(datetime):
   at=datetime(2026,10,28,7,15,tzinfo=__import__('zoneinfo').ZoneInfo('Europe/Moscow'))
   @classmethod
   def now(cls,tz=None):return cls.at
  page=dict(kind='drr:001',family='drr',page=1,total=1,bytes=b'PNG',actions=[])
  with patch.dict(os.environ,{'GITHUB_REPOSITORY':'Ekaterina11098/veschi-bot-runner','GITHUB_REF':'refs/heads/main','CHINA_AD_PREPARE_ONLY':'false'}),patch.object(daily,'datetime',Clock),patch.object(daily,'IO',return_value=cache),patch.object(daily,'telegram_sender',return_value=lambda _:None),patch('china_advertising_v2.prepare',return_value={'presentation':'three_day_attention_table_v4'}) as collect,patch('china_advertising_v2_png.render',return_value=[page]),patch.object(daily,'deliver',return_value={'status':'delivered','parts':[]}) as send:
   daily.run()
   self.assertIsNotNone(cache.get('china_agent:advertising_artifacts:2026-10-28:v2'))
   send.assert_not_called()
   Clock.at=Clock.at.replace(hour=7,minute=30)
   daily.run()
   self.assertEqual(collect.call_count,1)
   self.assertEqual(send.call_count,1)

class InvalidatedPlanTests(unittest.TestCase):
 def test_withdrawn_plan_cannot_reach_marketplace(self):
  from china_daily_ad_actions import execute
  from test_china_advertising_v2 import Fake
  cache=Fake();cache.validate_owner=lambda _:None
  with self.assertRaisesRegex(ValueError,'invalidated'):
   execute(cache,{},dict(invalidated_at='2026-10-27T05:00:00Z'))

class FrozenDeliveryTests(unittest.TestCase):
 def test_delivery_stage_cannot_fall_back_to_marketplace_collection(self):
  import os,china_advertising_daily as daily
  from test_china_advertising_v2 import Fake
  class Clock(datetime):
   @classmethod
   def now(cls,tz=None):return datetime(2026,10,28,7,30,tzinfo=__import__('zoneinfo').ZoneInfo('Europe/Moscow'))
  with patch.dict(os.environ,{'GITHUB_REPOSITORY':'Ekaterina11098/veschi-bot-runner','GITHUB_REF':'refs/heads/main','CHINA_AD_FROZEN_ONLY':'true'}),patch.object(daily,'datetime',Clock),patch.object(daily,'IO',return_value=Fake()),patch('china_advertising_v2.prepare') as collect,patch.object(daily,'telegram_sender') as send:
   with self.assertRaisesRegex(ValueError,'preparation missing'):daily.run()
   collect.assert_not_called();send.assert_not_called()


class LaunchDayTests(unittest.TestCase):
 def test_launch_day_spend_is_preserved_but_not_used_for_exclusion(self):
  from china_advertising_v2 import build
  c=campaign();c['timestamps']=dict(created='2026-10-26T18:00:00+03:00',started='2026-10-26T21:15:00+03:00')
  def raw(day,spend):
   nm=dict(nmId=1,sum=spend,sum_price=0,orders=0,views=100,clicks=100)
   return dict(date=day+'T00:00:00Z',sum=spend,sum_price=0,orders=0,views=100,clicks=100,apps=[dict(nms=[nm])])
  source=dict(period_to='2026-10-27',observed_at='2026-10-28T04:15:00Z',ids=[12],config={'minTopUp':10000},catalogue={'rows':[dict(nmID=1,vendorCode='fixture',price=100)]},executions=[],batches={'0':dict(campaigns={'adverts':[c]},budgets={'adverts':[dict(advertId=12,currency='CNY',total=100)]},stats=[dict(advertId=12,days=[raw('2026-10-26',50),raw('2026-10-27',0)])])})
  result=build(source)['campaigns'][0]
  self.assertEqual(result['period']['spend'],50)
  self.assertFalse(any(r.get('action') for r in result['focus']))

if __name__=='__main__':unittest.main()

