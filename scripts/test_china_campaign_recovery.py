import copy,sys,types,unittest
from datetime import datetime,timezone
from unittest.mock import patch
from china_campaign_recovery import execute

class Recovery(unittest.TestCase):
 def fixture(self,fail=None):
  c=dict(id=12,status=11,currency='CNY',bid_type='manual',settings=dict(payment_type='cpc',placements=dict(search=True)),nm_settings=[dict(nm_id=20,bids_kopecks=dict(search=27))]);cash=[0];calls=[]
  e=dict(period_to='2026-11-13',observed_at=datetime.now(timezone.utc).isoformat(),modeled_after_ads_cny=10,stress_after_ads_cny=5,preliminary=True,expected_bids={'20':dict(search=27)},member_inputs={'20':dict(price=30,cost=10)})
  item=dict(kind='recover_campaign',campaign_id=12,recovery_evidence=e,placement='search',target_minor=23,balance_before=0,amount_cny=100);state={}
  def req(path,method='GET',body=None):
   if path.endswith('/bids/min'):return dict(bids=[dict(nm_id=20,bids=[dict(type='search',currency='CNY',value=23 if fail!='minimum'else 24)])])
   if path.endswith('/config'):return dict(currency='CNY',minTopUp=10000)
   if path.endswith('/balance'):return dict(currency='CNY',balance=1000)
   calls.append(path)
   if path.endswith('/bids'):c['nm_settings'][0]['bids_kopecks']['search']=23
   elif 'deposit' in path:
    if fail=='fund':raise RuntimeError('uncertain deposit')
    cash[0]=100
   elif '/start' in path:c['status']=9
   return {}
  helpers=dict(current_prices=lambda *a:dict(rows=[dict(nm_id=20,article='A',seller_price=30)]),published_stock=lambda *a:dict(missing_nm_ids=[],amounts={'20':10}))
  stock=types.SimpleNamespace(read_stock=lambda *a:dict(coverage_complete=True,rows=[dict(article='A',price=1000,stock=10,reserve=0)]))
  ctx=patch.dict(sys.modules,{'china_morning_readiness':types.SimpleNamespace(**helpers),'china_moysklad_read':stock})
  args=(types.SimpleNamespace(get=lambda k:{}),item,state,lambda:None,req,lambda cid:copy.deepcopy(c),lambda cid:cash[0])
  return ctx,args,calls
 def test_all_steps_verified_and_no_replay(self):
  ctx,args,calls=self.fixture()
  with ctx:
   self.assertEqual(execute(*args),3);self.assertEqual(args[2]['status'],'verified')
   with self.assertRaises(ValueError):execute(*args)
  self.assertEqual(len(calls),3)
 def test_uncertain_funding_prevents_start(self):
  ctx,args,calls=self.fixture('fund')
  with ctx:
   with self.assertRaises(RuntimeError):execute(*args)
  self.assertEqual(args[2]['status'],'uncertain');self.assertFalse(any('/start' in x for x in calls))
 def test_changed_minimum_prevents_any_write(self):
  ctx,args,calls=self.fixture('minimum')
  args[1]['target_minor']=22
  with ctx:
   with self.assertRaises(AssertionError):execute(*args)
  self.assertEqual(calls,[])
 def test_old_temporary_hold_released_only_after_verified_restart(self):
  ctx,args,calls=self.fixture();args=list(args);policy=dict(do_not_fund={'12':'old temporary hold'});writes=[]
  args[0]=types.SimpleNamespace(get=lambda k:copy.deepcopy(policy),put=lambda k,v:writes.append((k,v)))
  args[1]['supersedes_temporary_hold']='old temporary hold'
  with ctx:execute(*args)
  self.assertEqual(args[2]['status'],'verified');self.assertEqual(len(writes),1)
  self.assertNotIn('12',writes[0][1]['do_not_fund']);self.assertFalse(writes[0][1]['released_temporary_hold_12']['grants_standing_funding_permission'])
if __name__=='__main__':unittest.main()
