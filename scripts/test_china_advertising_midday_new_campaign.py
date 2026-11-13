import copy,unittest
from unittest.mock import patch
from china_midday_completed_review import completed_campaign_stats
class CampaignHistory(unittest.TestCase):
 def state(self,cid=119,created='2026-11-04T13:58:03+03:00'):
  return dict(id=cid,timestamps=dict(created=created))
 def test_new_campaign_does_not_request_impossible_history(self):
  with patch('china_midday_completed_review.http',side_effect=AssertionError('No past request')):
   r=completed_campaign_stats(None,[self.state()],{},'2026-10-28','2026-11-03')
  self.assertEqual([],r[119]['days']);self.assertEqual('created_after_completed_window',r[119]['history_status'])
 def test_timezone_uses_msk_date(self):
  with patch('china_midday_completed_review.http',side_effect=AssertionError('No past request')):
   r=completed_campaign_stats(None,[self.state(created='2026-11-03T21:30:00Z')],{},'2026-10-28','2026-11-03')
  self.assertEqual([],r[119]['days'])
 def test_null_for_old_campaign_is_unknown_not_zero(self):
  with patch('china_midday_completed_review.http',return_value=None):
   with self.assertRaisesRegex(ValueError,'history unavailable'):completed_campaign_stats(None,[self.state(created='2026-11-02T13:00:00+03:00')],{},'2026-10-28','2026-11-03')
 def test_empty_list_does_not_zero_old_campaign(self):
  with patch('china_midday_completed_review.http',return_value=[]):
   with self.assertRaisesRegex(ValueError,'history incomplete'):completed_campaign_stats(None,[self.state(created='2026-11-02T13:00:00+03:00')],{},'2026-10-28','2026-11-03')
 def test_created_on_last_completed_day_requires_real_history(self):
  raw=dict(advertId=119,days=[dict(date='2026-11-03T00:00:00Z',sum=9)])
  with patch('china_midday_completed_review.http',return_value=[raw])as req:
   r=completed_campaign_stats(None,[self.state(created='2026-11-03T20:00:00+03:00')],{},'2026-10-28','2026-11-03')
  self.assertEqual(9,r[119]['days'][0]['sum']);self.assertEqual(1,req.call_count)
 def test_real_current_metrics_and_original_source_not_modified(self):
  saved={1:dict(advertId=1,days=[dict(date='2026-11-03',sum=7)])};before=copy.deepcopy(saved)
  with patch('china_midday_completed_review.http',side_effect=AssertionError('No past request')):
   r=completed_campaign_stats(None,[self.state(1),self.state()],saved,'2026-10-28','2026-11-03')
  r[1]['days'][0]['sum']=99;self.assertEqual(before,saved)
 def test_missing_creation_cannot_invent_empty_history(self):
  with patch('china_midday_completed_review.http',return_value=None):
   with self.assertRaises(ValueError):completed_campaign_stats(None,[dict(id=119,timestamps={})],{},'2026-10-28','2026-11-03')
 def test_owner_skip_returns_before_collect_render_or_send(self):
  import os,sys,types
  import china_advertising_midday as m
  io=types.SimpleNamespace(get=lambda key:dict(status='skipped_by_owner'))
  price=types.ModuleType('china_advertising_state');price.AdvertisingIO=lambda:io
  delivery=types.ModuleType('china_advertising_delivery');delivery.deliver=lambda *a,**kw:self.fail('Delivery forbidden');delivery.telegram_sender=lambda *a:self.fail('Sender forbidden')
  actions=types.ModuleType('china_daily_ad_actions');actions.plan=lambda *a:self.fail('Plan forbidden');actions.bind=lambda *a:self.fail('Bind forbidden')
  with patch.dict(os.environ,{'GITHUB_REPOSITORY':'Ekaterina11098/veschi-bot-runner','GITHUB_REF':'refs/heads/main'}),patch.dict(sys.modules,{'china_advertising_state':price,'china_advertising_delivery':delivery,'china_daily_ad_actions':actions}),patch.object(m,'collect',side_effect=AssertionError('No collection')):
   m.run()
if __name__=='__main__':unittest.main()
