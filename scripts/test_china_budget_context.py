import unittest
from datetime import datetime,timezone
from china_budget_context import KEY,decision,read_context,dialog_context

NOW=datetime(2026,10,27,10,20,tzinfo=timezone.utc)
class W:
 now=NOW
 def __init__(self,p):self.p=p
 def get(self,k):assert k==KEY;return self.p

def context():
 return dict(status='active',mode='manual_only',observed_at='2026-10-27T10:15:05Z',
 valid_until='2026-10-28T04:30:00Z',campaigns={'41298169':dict(status='pending_manual',balance_at_review=20,remaining_manual_cny=400)})

class FundingRegression(unittest.TestCase):
 def test_today_high_or_no_orders_does_not_veto_agreed_test(self):
  for today in (7.17,None,100):
   text=decision('41298169',dict(drr_today=today,drr_3days=9,proposed=50),{},context(),20)
   self.assertIn('400 CNY',text);self.assertIn('вручную',text)
   self.assertNotIn('не рекомендовано',text)
 def test_context_expired_or_revoked_not_used(self):
  p=context();p['valid_until']='2026-10-27T10:19:00Z'
  self.assertEqual({},read_context(W(p).get,NOW))
  p=context();p['status']='revoked'
  self.assertEqual({},read_context(W(p).get,NOW))
 def test_funded_and_changed_balance_do_not_repeat(self):
  p=context();p['campaigns']['41298169']['status']='manual_funded'
  self.assertNotIn('400 CNY',decision('41298169',{}, {},p,317))
  self.assertNotIn('400 CNY',decision('41298169',{}, {},context(),317))
 def test_other_campaign_does_not_inherit_agreement(self):
  self.assertNotIn('400 CNY',decision('41332083',{}, {},context(),10))
 def test_missing_economics_does_not_say_funds_sufficient(self):
  s=decision('1',dict(drr_today=None),{}, {},10)
  self.assertIn('риск окончания',s);self.assertIn('не означает',s)
  self.assertNotIn('не рекомендовано',s)
 def test_context_never_authorizes_writes(self):
  p=read_context(W(context()).get,NOW)
  self.assertFalse(p['execution_authorized']);self.assertFalse(p['automatic_funding'])
 def test_short_reply_loads_saved_amount_only_in_work_group(self):
  w=W(context());job=dict(chat_id=-1004342917488,request_text='пополни')
  self.assertEqual(400,dialog_context(w,job,'Бюджет РК 41298169')['campaigns']['41298169']['remaining_manual_cny'])
  job['chat_id']=123;self.assertEqual({},dialog_context(w,job,'Бюджет РК 41298169'))
 def test_bad_timestamps_fail_closed(self):
  p=context();p['valid_until']='wrong';self.assertEqual({},read_context(W(p).get,NOW))

if __name__=='__main__':unittest.main()
