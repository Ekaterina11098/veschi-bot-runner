import unittest,copy
from datetime import datetime,timezone
from china_advertising_growth import shortlist,assess,merge
NOW=datetime(2026,10,31,7,tzinfo=timezone.utc)
def source():
 c=dict(id=7,status=9,currency='CNY',bid_type='manual',settings=dict(payment_type='cpc',placements=dict(search=True,recommendations=False)),timestamps=dict(started='2026-10-20T00:00:00+03:00'),nm_settings=[dict(nm_id=10,bids_kopecks=dict(search=28,recommendations=0))])
 days=[dict(date=d+'T00:00:00Z',apps=[dict(nms=[dict(nmId=10,sum=14,sum_price=600,orders=3,clicks=50,views=1000)])])for d in ['2026-10-28','2026-10-29','2026-10-30','2026-10-31']]
 return dict(period_to='2026-10-30',executions=[],batches={'0':dict(campaigns=dict(adverts=[c]),stats=[dict(advertId=7,days=days)])})
def evidence():
 return dict(observed_at=NOW.isoformat(),stock_observed_at=NOW.isoformat(),prices_observed_at=NOW.isoformat(),buyout_observed_at=NOW.isoformat(),cabinet='token_3',currency='CNY',stock_free=30,published_stock=20,rating=4.8,finished=40,paid=20,expected_margin_before_ads_cny=30,stress_margin_before_ads_cny=10,minimum_minor=28,article='10-test',negative_experience_requires_review=False)
CFG=dict(currency='CNY',cpcStep=1,cpcMaxBid=1290)
class Growth(unittest.TestCase):
 def test_completed_days_and_exact_step(self):
  rows=shortlist(source());self.assertEqual(len(rows),1);self.assertEqual(rows[0]['metrics']['orders'],9)
  a=assess(rows[0],evidence(),CFG,NOW);self.assertEqual(a['target_minor'],31);self.assertEqual(a['direction'],'raise')
 def test_missing_day_is_not_zero(self):
  s=source();s['batches']['0']['stats'][0]['days'].pop(1);self.assertEqual(shortlist(s),[])
 def test_change_day_excluded(self):
  s=source();c=s['batches']['0']['campaigns']['adverts'][0];before=copy.deepcopy(c);before['nm_settings'][0]['bids_kopecks']['search']=25
  s['executions']=[dict(payload=dict(status='verified',before=before,after=c,verified_at='2026-10-29T10:00:00+03:00'))]
  self.assertEqual(shortlist(s),[])
 def test_today_not_used(self):
  s=source();s['batches']['0']['stats'][0]['days'][-1]['apps'][0]['nms'][0]['orders']=0
  self.assertEqual(shortlist(s)[0]['metrics']['orders'],9)
 def test_unknown_rating_and_stock(self):
  r=shortlist(source())[0]
  for k in ['rating','stock_free','published_stock']:
   e=evidence();e[k]=0;self.assertIsNone(assess(r,e,CFG,NOW))
 def test_unknown_or_stale_economics(self):
  r=shortlist(source())[0]
  for e in [{},dict(evidence(),observed_at='2026-10-25T00:00:00Z'),dict(evidence(),stress_margin_before_ads_cny=1)]:self.assertIsNone(assess(r,e,CFG,NOW))
 def test_negative_experience_requires_review(self):
  self.assertIsNone(assess(shortlist(source())[0],dict(evidence(),negative_experience_requires_review=True),CFG,NOW))
 def test_reduction_takes_precedence(self):
  a=assess(shortlist(source())[0],evidence(),CFG,NOW);b=dict(campaigns=[dict(id=7,attention=[dict(action=dict(nm_id=10))])]);self.assertEqual(len(merge(b,[a])['campaigns'][0]['attention']),1)
 def test_only_action_no_explanation_in_report(self):
  from china_advertising_v2_png import recommendations
  self.assertEqual(recommendations(dict(attention=[],notes=['not a recommendation'])),['Не требуется'])
  a=assess(shortlist(source())[0],evidence(),CFG,NOW);b=merge(dict(campaigns=[dict(id=7,attention=[])]),[a]);out=recommendations(b['campaigns'][0]);self.assertEqual(len(out),1);self.assertIn('Повысить',out[0]);self.assertNotIn('маржа',out[0])
 def test_pavel_cannot_repeat_owner_completed_budget(self):
  from unittest.mock import patch
  from china_daily_ad_actions import handle,BIND
  from china_loss_control import PLAN,digest
  p=dict(plan_id='funded',chat_id=-1004342917488,plan_sha256=digest([]),items=[],report_message_ids=[546],expires_at='2020-01-01T00:00:00+00:00',owner_completed_budget_receipts=['verified-owner-receipt'])
  class W:
   now=NOW
   def get(self,key):return {BIND+'546':dict(plan_id='funded',plan_sha256=digest([])),PLAN+'funded':p}.get(key)
   def save(self,*args,**kwargs):raise AssertionError('Must not create another approval')
  job=dict(request_text='Делай все',sender_id=307200273,tool_trace=[dict(name='china_saved_question',bot_id=8780468043,reply_message_id=546)])
  with patch('china_daily_selected.handle',return_value=None),patch('china_group_permissions.allowed',return_value=True):
   answer,trace=handle(W(),job)
  self.assertIn('уже выполнены',answer);self.assertEqual(trace,[])
if __name__=='__main__':unittest.main()
