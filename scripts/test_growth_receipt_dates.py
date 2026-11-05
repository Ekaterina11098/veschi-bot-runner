import sys,types,unittest
from datetime import datetime,timezone
from unittest.mock import patch
import china_advertising_growth as g
from event_time_fixture import event_time
class ReachedPrice(Exception):pass
class Tests(unittest.TestCase):
 def context(self,at):
  now=datetime(2026,11,5,0,10,tzinfo=timezone.utc)
  class Clock:
   @staticmethod
   def now(tz=None):return now
  fake=types.ModuleType('china_advertising_v2');fake.event_time=event_time
  requests=types.ModuleType('requests');calls=[]
  def get(url,**kw):
   calls.append(url)
   if '/config' not in url:raise ReachedPrice()
   return types.SimpleNamespace(raise_for_status=lambda:None,json=lambda:dict(currency='CNY',cpcStep=1,cpcMaxBid=100))
  requests.get=get
  receipt=dict(status='verified',submitted_at=at,before={'nm_settings':[{'nm_id':10,'bids_kopecks':{'recommendations':28}}]},after={'nm_settings':[{'nm_id':10,'bids_kopecks':{'recommendations':30}}]})
  io=types.SimpleNamespace(token='fixture',get=lambda k:{'1':'receipt'} if k=='china_agent:verified_campaign_state:v1' else receipt)
  item=dict(direction='raise',nm_id=10,old_minor=28,target_minor=30,growth_evidence=dict(observed_at=now.isoformat(),period_to='2026-11-04',stress_margin_before_ads_cny=100,modeled_cpa_same_cr=5))
  return Clock,fake,requests,io,item,calls
 def test_legacy_utc_history_passes_date_check(self):
  clock,fake,requests,io,item,calls=self.context('2026-10-29 19:14:50 UTC')
  with patch.dict(sys.modules,{'china_advertising_v2':fake,'requests':requests}),patch.object(g,'datetime',clock),self.assertRaises(ReachedPrice):g.validate_raise(io,item,{})
  self.assertEqual(len(calls),2)
 def test_same_msk_day_still_blocks_across_utc_midnight(self):
  clock,fake,requests,io,item,calls=self.context('2026-11-04 23:00:00 UTC')
  with patch.dict(sys.modules,{'china_advertising_v2':fake,'requests':requests}),patch.object(g,'datetime',clock),self.assertRaisesRegex(ValueError,'already raised today'):g.validate_raise(io,item,{})
  self.assertEqual(len(calls),1)
 def test_equivalent_offsets(self):
  self.assertEqual(event_time('2026-10-29 19:14:50 UTC'),event_time('2026-10-29T22:14:50+03:00'))
  self.assertEqual(event_time('2026-10-29T19:14:50Z'),event_time('2026-10-29 19:14:50 UTC'))
 def test_unknown_timezone_not_silently_assumed(self):
  with self.assertRaisesRegex(ValueError,'timezone'):event_time('2026-10-29 19:14:50')
 def test_freshness_uses_same_parser(self):
  fake=types.ModuleType('china_advertising_v2');fake.event_time=event_time
  with patch.dict(sys.modules,{'china_advertising_v2':fake}):
   self.assertTrue(g.fresh('2026-11-05 00:00:00 UTC',datetime(2026,11,5,0,10,tzinfo=timezone.utc),2))
   self.assertFalse(g.fresh('2026-11-05 00:00:00',datetime(2026,11,5,0,10,tzinfo=timezone.utc),2))
if __name__=='__main__':unittest.main()

