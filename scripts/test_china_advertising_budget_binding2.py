import unittest,copy
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from china_budget_page_actions import page_action,owner_policy
from china_daily_ad_actions import execute,plan,handle,BIND
from china_loss_control import PLAN,digest
class IO:
 def __init__(self):self.data={};self.now=datetime.now(timezone.utc);self.sent=[]
 def get(self,k):return copy.deepcopy(self.data.get(k))
 def put(self,k,v):self.data[k]=copy.deepcopy(v)
 def create(self,k,v):
  if k in self.data:return False
  self.put(k,v);return True
 def save(self,k,v,insert=False):return self.create(k,v)if insert else self.put(k,v)
 def validate_owner(self,a):pass
 def tg(self,name,body):self.sent.append(body);return dict(message_id=900,chat=dict(id=-1004342917488),from_=None,**{'from':dict(id=8780468043)})
class BudgetBindings(unittest.TestCase):
 def row(self):return dict(id=12,status=9,budget_review_required=True,budget_reserve_amount=400,budget_action=None,budget_economics_reason='Нужна свежая экономика')
 def test_displayed_reserve_is_only_a_recommendation(self):
  self.assertIsNone(page_action(self.row(),dict(budget_days=['2026-10-30','2026-10-31','2026-11-01'])))
 def test_unknown_amount_has_no_fake_zero_action(self):
  c=self.row();c['budget_reserve_amount']=None;self.assertIsNone(page_action(c,{}))
 def test_ready_topup_remains_ready_and_unchanged(self):
  c=self.row();c['budget_action']=dict(kind='topup_campaign',amount_cny=400)
  self.assertEqual(page_action(c,{}),c['budget_action'])
 def test_owner_refusal_and_view_only_have_no_actions(self):
  c=self.row();c['owner_budget_refused']=True;self.assertIsNone(page_action(c,{}))
  c=self.row();self.assertIsNone(page_action(c,dict(view_only=True)))
 def test_old_conditional_plan_is_blocked_without_budget_approval(self):
  io=IO();item=dict(id='reserve:12',kind='approve_budget_reserve',campaign_id=12,amount_cny=400)
  p=dict(plan_id='fixture',execution_kind='daily_ad_actions_v2',items=[item],plan_sha256=digest([item]),expires_at=(io.now+timedelta(hours=1)).isoformat())
  a=dict(job_id=777,input_message_id=888,plan_sha256=p['plan_sha256'])
  with patch('time.sleep'):e=execute(io,a,p)
  self.assertEqual(e['wb_writes'],0);self.assertEqual(e['items'][0]['status'],'blocked')
  self.assertIsNone(io.get('china_agent:budget_amount_approval:v1:fixture:12'))
if __name__=='__main__':unittest.main()
