import copy,hashlib,types,unittest
from china_confirmed_funding_context import reconcile
from china_loss_control import PLAN,APPROVAL
class Funding(unittest.TestCase):
 def fixture(self):
  cid=12;old=dict(id=cid,status=9,settings=dict(payment_type='cpc'),nm_settings=[dict(nm_id=20,bids_kopecks=dict(search=27))]);after=copy.deepcopy(old);after['nm_settings'][0]['bids_kopecks']['search']=23
  item=dict(id='bid',kind='ad_set_bid',campaign_id=cid,nm_id=20,old_minor=27,target_minor=23,placement='search')
  parent=dict(plan_id='parent',plan_sha256='hash',report_generation='pair-drr',family='drr',period_to='2026-11-14')
  token=hashlib.sha256(b'parent:hash:drr').hexdigest()[:24]+'-7';child=dict(plan_id='parent-buttons-'+token,plan_sha256='childhash',items=[item])
  cache={'china_agent:daily_ad_current_report:v1:drr':dict(plan_id='parent'),PLAN+'parent':parent,PLAN+child['plan_id']:child,APPROVAL+'1':dict(plan_id=child['plan_id'],sender_id=7,status='approved'),'china_agent:report_buttons:v1:confirmation:'+token:dict(status='confirmed',sender_id=7,plan_sha256='hash',selected_ids=['bid'],job_id=1),'china_agent:daily_ad_execution:v2:'+child['plan_id']:dict(plan_sha256='childhash',items=[dict(id='bid',status='verified',before=old,after=after)])}
  io=types.SimpleNamespace(daily_report_plan=dict(report_generation='pair-budgets',family='budgets',period_to='2026-11-14'),daily_report_approval=dict(sender_id=7),get=lambda k:cache.get(k))
  e=dict(expected_bids={'20':dict(search=27)},member_inputs={'20':dict(price=10)},modeled_after_ads_cny=100)
  return io,e,after,cache
 def test_only_verified_companion_delta_reconciled_without_profit_credit(self):
  io,e,c,_=self.fixture();out=reconcile(io,e,c);self.assertEqual(out['expected_bids'],{'20':dict(search=23)});self.assertEqual(out['modeled_after_ads_cny'],100);self.assertEqual(e['expected_bids']['20']['search'],27)
 def test_unapproved_current_bid_rejected(self):
  io,e,c,_=self.fixture();c['nm_settings'][0]['bids_kopecks']['search']=24
  with self.assertRaises(ValueError):reconcile(io,e,c)
 def test_different_actor_rejected(self):
  io,e,c,_=self.fixture();io.daily_report_approval['sender_id']=8
  with self.assertRaises(ValueError):reconcile(io,e,c)
 def test_uncertain_never_treated_as_verified(self):
  io,e,c,cache=self.fixture();key=next(k for k in cache if k.startswith('china_agent:daily_ad_execution'))
  cache[key]['items'][0]['status']='uncertain'
  with self.assertRaises(ValueError):reconcile(io,e,c)
if __name__=='__main__':unittest.main()
