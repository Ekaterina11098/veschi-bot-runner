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
 def test_displayed_conditional_amount_has_hash_bound_action(self):
  io=IO();x=page_action(self.row(),dict(budget_days=['2026-10-30','2026-10-31','2026-11-01']))
  p=plan(io,'2026-11-02',dict(family='budgets',actions=[x]),0)
  self.assertEqual(len(p['items']),1);self.assertEqual(p['items'][0]['amount_cny'],400);self.assertEqual(p['plan_sha256'],digest([x]))
 def test_unknown_amount_has_no_fake_zero_action(self):
  c=self.row();c['budget_reserve_amount']=None;self.assertIsNone(page_action(c,{}))
 def test_ready_topup_remains_ready_and_unchanged(self):
  c=self.row();c['budget_action']=dict(kind='topup_campaign',amount_cny=400)
  self.assertEqual(page_action(c,{}),c['budget_action'])
 def test_owner_refusal_and_view_only_have_no_actions(self):
  c=self.row();c['owner_budget_refused']=True;self.assertIsNone(page_action(c,{}))
  c=self.row();self.assertIsNone(page_action(c,dict(view_only=True)))
 def test_conditional_execution_records_approval_not_WB_success(self):
  io=IO();item=page_action(self.row(),{})
  p=dict(plan_id='fixture',execution_kind='daily_ad_actions_v2',items=[item],plan_sha256=digest([item]),expires_at=(io.now+timedelta(hours=1)).isoformat())
  a=dict(job_id=777,input_message_id=888,plan_sha256=p['plan_sha256'])
  with patch('time.sleep'):
   e=execute(io,a,p)
  self.assertEqual(e['wb_writes'],0);self.assertEqual(e['items'][0]['status'],'approved_pending_conditions')
  self.assertIn('пополнение не выполнено',io.sent[0]['text']);self.assertNotIn('проверено WB',io.sent[0]['text'])
  self.assertEqual(io.get('china_agent:budget_amount_approval:v1:fixture:12')['amount_cny'],400)
 def test_forbidden_campaign_cannot_be_approved_by_stale_plan(self):
  io=IO();io.put('china_agent:budget_owner_policy:v1',dict(do_not_fund={'12':'owner'}));item=page_action(self.row(),{})
  p=dict(plan_id='fixture2',execution_kind='daily_ad_actions_v2',items=[item],plan_sha256=digest([item]),expires_at=(io.now+timedelta(hours=1)).isoformat())
  e=execute(io,dict(plan_sha256=p['plan_sha256']),p)
  self.assertEqual(e['items'][0]['status'],'blocked');self.assertEqual(e['wb_writes'],0)
if __name__=='__main__':unittest.main()
