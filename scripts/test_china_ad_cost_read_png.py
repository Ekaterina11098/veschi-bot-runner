import unittest,copy,base64,hashlib
from datetime import datetime,timezone
from types import SimpleNamespace
from china_ad_cost_collect import allowed_read,read_scope
from china_ad_cost_png import render,photo,PREFIX
from china_three_day_ads import build,load,periods
from test_china_three_day_ads import source,row
class ReadAndPng(unittest.TestCase):
 def test_guard_forbids_writes_and_wrong_cabinet(self):
  endpoint='https://mcp.mpstats.io/mcp'
  payload=lambda n,a:dict(method='tools/call',params=dict(name=n,arguments=a))
  self.assertFalse(allowed_read('POST',endpoint,payload('account_limits',{})))
  with read_scope(['2026-10-22']) as scope:
   scope['campaigns']={1}
   good=payload('wbbidder_campaign_stats',dict(campaign_id=1,report='products',d1='2026-10-22',d2='2026-10-22'))
   self.assertTrue(allowed_read('POST',endpoint,good))
   for bad in (payload('wbbidder_update_bid',{}),payload('lk_wb_cabinets',{'action':'select'}),payload('wbbidder_campaigns',{'tokens':[1],'report':'state'})):
    self.assertFalse(allowed_read('POST',endpoint,bad))
   self.assertFalse(allowed_read('PATCH',endpoint,good))
   self.assertFalse(allowed_read('POST','https://advert-api.wildberries.ru/adv/v0/pause',good))
 def test_frozen_hash_and_scope(self):
  b=b'image';key='key'
  manifest=dict(status='frozen',chat_id=1,job_id=7,days=['2026-10-20','2026-10-22'],files=[dict(data=base64.b64encode(b).decode(),sha256=hashlib.sha256(b).hexdigest())])
  w=SimpleNamespace(active_question_id=7,get=lambda k:manifest)
  self.assertEqual(photo(w,1,PREFIX+key+':0')[0],b)
  with self.assertRaises(PermissionError):photo(w,2,PREFIX+key+':0')
  with self.assertRaises(ValueError):photo(w,1,PREFIX+key+':-1')
  manifest['files'][0]['data']=base64.b64encode(b'bad').decode()
  with self.assertRaises(ValueError):photo(w,1,PREFIX+key+':0')
 def test_render_long_period_only_filters_whole_trend(self):
  days=periods('2026-10-23',7)
  sources=[source(d,[row(i+1,1,100)]) for i,d in enumerate(days)]
  result=build(sources,'2026-10-23',count=7)
  pages=render(result,{'1':'Оставить цену'})
  self.assertEqual(len(pages),2)
  self.assertTrue(all(p.startswith(b'\x89PNG') for p in pages))
  sources[3]=source(days[3],[row(1,1,100)])
  self.assertEqual(len(render(build(sources,'2026-10-23',count=7),{})),1)
 def test_load_batches_existing_sources_without_collection(self):
  days=periods('2026-10-23',5)
  values=[dict(cache_key='china_agent:advertising_source:'+str(__import__('datetime').date.fromisoformat(d)+__import__('datetime').timedelta(days=1))+':v1',payload=source(d,[row(1,1,100)])) for d in days]
  calls=[]
  w=SimpleNamespace(now=datetime(2026,10,23,tzinfo=timezone.utc),db=lambda *a,**k:(calls.append(k) or values))
  self.assertEqual(len(load(w,5)),5);self.assertEqual(len(calls),1)
if __name__=='__main__':unittest.main()
