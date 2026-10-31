import copy,unittest
from datetime import datetime,timezone
from china_experiment_journal import ROOT,context,guard,receipt_changes,risk_limits,summarize_observation,window
class W:
 now=datetime(2026,10,31,19,5,tzinfo=timezone.utc)
 def __init__(self):self.mem={};self.writes=[]
 def get(self,k):return copy.deepcopy(self.mem.get(k))
 def save(self,k,v,insert=False):
  if insert and k in self.mem:return False
  self.mem[k]=copy.deepcopy(v);self.writes.append(k);return True
 def catalog(self):return [('1473243895','045-NoelBag-ginger'),('1473245494','143-ReginaBag-black')]
 def db(self,method,table,params):
  assert method=='GET' and table=='telegram_api_cache'
  prefix=params['cache_key'][5:-1]
  rows=[dict(cache_key=k,payload=copy.deepcopy(v)) for k,v in self.mem.items() if k.startswith(prefix)]
  return rows[params.get('offset',0):params.get('offset',0)+params['limit']]
def campaign(bid,other=28):
 return dict(id=40933588,nm_settings=[dict(nm_id=1473243895,bids_kopecks=dict(search=0,recommendations=bid)),dict(nm_id=1473245494,bids_kopecks=dict(search=0,recommendations=other))])
def receipt():
 return dict(status='verified',submitted_at='2026-10-31T19:01:59+00:00',verified_at='2026-10-31T19:02:05+00:00',before=campaign(50),after=campaign(28))
class Journal(unittest.TestCase):
 def test_045_exact_change_only_not_whole_campaign(self):
  changes=receipt_changes('receipt',receipt())
  self.assertEqual(len(changes),1);self.assertEqual(changes[0]['nm_id'],1473243895)
  self.assertEqual((changes[0]['before'],changes[0]['after']),(50,28))
 def test_uncertain_receipt_not_verified_history(self):
  r=receipt();r['status']='uncertain';self.assertEqual(receipt_changes('receipt',r),[])
 def test_registry_catches_new_045_and_first_full_day(self):
  w=W();w.mem['receipt']=receipt();w.mem['china_agent:verified_campaign_state:v1']={'40933588':'receipt'}
  j=context(w,[1473243895]);g=guard(j,1473243895,w.now)
  self.assertFalse(g['allowed']);self.assertEqual(g['first_full_day'],'2026-11-01')
  self.assertEqual(g['first_review_at_msk'],'2026-11-02T00:00:00+03:00')
  self.assertFalse(j['grants_action_permission'])
  w.now=datetime(2026,11,2,0,1,tzinfo=timezone.utc);self.assertTrue(guard(j,1473243895,w.now)['allowed'])
 def test_143_price_day_excluded_until1nov(self):
  change=dict(at='2026-10-30T15:19:00+00:00')
  today=window(change,W.now);self.assertEqual(today['first_full_day'],'2026-10-31');self.assertEqual(today['completed_days'],0)
  self.assertEqual(window(change,datetime(2026,11,1,0,tzinfo=timezone.utc))['completed_days'],1)
 def test_143_registered_price_receipt_is_read_without_fake_ad_action(self):
  w=W();w.mem[ROOT+'policy']=dict(additional_receipt_keys=['price143'])
  w.mem['price143']=dict(status='verified',kind='price_change',cabinet='token_3',verified_at='2026-10-30T15:19:28Z',before=dict(nmID=1473245494,currencyIsoCode4217='CNY',sizes=[dict(discountedPrice=450.5)]),after=dict(nmID=1473245494,vendorCode='143-ReginaBag-black',currencyIsoCode4217='CNY',sizes=[dict(discountedPrice=495.55)]))
  j=context(w,[1473245494]);event=j['latest_by_nm']['1473245494']
  self.assertEqual(event['kind'],'price');self.assertEqual(event['after'],495.55)
  self.assertEqual(event['window']['first_full_day'],'2026-10-31')
 def test_journal_immutable_and_idempotent(self):
  w=W();w.mem['receipt']=receipt();w.mem['china_agent:verified_campaign_state:v1']={'40933588':'receipt'}
  context(w,[1473243895]);keys=list(w.writes);context(w,[1473243895]);self.assertEqual(w.writes,keys)
  self.assertTrue(all(k.startswith(ROOT+'event:') for k in keys))
 def test_no_observations_means_pending_not_success(self):
  self.assertEqual(summarize_observation({})['status'],'pending')
 def test_green_execution_or_drr_does_not_prove_profit(self):
  e=dict(advertising_outcome='positive',observations=[dict(before=dict(days=1,period_complete=True,currency='CNY'),after=dict(days=1,period_complete=True,currency='CNY',ad_drr=1),source_keys=['saved'],advertising_direction='positive')])
  a=summarize_observation(e);self.assertFalse(a['financial_comparison']);self.assertEqual(a['business_outcome'],'unconfirmed');self.assertEqual(a['causality'],'not_established')
 def test_missing_period_is_not_business_result(self):
  e=dict(observations=[dict(before=dict(days=1,period_complete=True),after=dict(days=1,period_complete=False),source_keys=['saved'])])
  self.assertEqual(summarize_observation(e)['status'],'inconclusive')
 def test_old_ad_drr_label_does_not_permanently_reject_positive_test(self):
  from china_experience import assess_candidate
  result=assess_candidate([dict(event_id='small',action=dict(nm_ids=[1473243895]),advertising_outcome='negative',business_outcome='inconclusive')],1473243895,{})
  self.assertFalse(result['needs_review']);self.assertEqual(result['risks'][0]['basis'],'advertising_only_not_profit')
class Limits(unittest.TestCase):
 def test_045_preliminary_economics(self):
  pre=.2*(235.2*.75-850.001197/12)-12.8-10/12
  r=risk_limits(pre,.2,5,bid_cny=.5)
  self.assertAlmostEqual(r['break_even_cpa_model_cny'],7.48,places=2)
  self.assertAlmostEqual(r['required_click_order_pct'],6.6845,places=3)
  self.assertEqual(r['suggested_initial_risk_budget_cny'],3.74)
  self.assertTrue(r['small_sample']);self.assertFalse(r['automatic_funding']);self.assertFalse(r['automatic_stop'])
 def test_unknown_buyout_and_costs_are_not_zero(self):
  self.assertFalse(risk_limits(None,.5,20)['available'])
  self.assertFalse(risk_limits(10,None,20)['available'])
 def test_zero_buyout_never_replaced_by50percent(self):
  r=risk_limits(-15,0,5);self.assertEqual(r['buyout'],0);self.assertEqual(r['suggested_initial_risk_budget_cny'],0)
 def test_sku_risk_not_multiplied_by_campaign_count(self):
  r=risk_limits(10,.5,20,spent_cny=3)
  self.assertEqual(r['suggested_initial_risk_budget_cny'],5);self.assertEqual(r['remaining_proposed_risk_cny'],2)
  self.assertIn('all campaigns',r['risk_scope']);self.assertFalse(r['execution_authorized'])
 def test_missing_spend_does_not_become_zero(self):
  self.assertIsNone(risk_limits(10,.5,20)['remaining_proposed_risk_cny'])
 def test_positive_small_test_not_proven_low_drr(self):
  r=risk_limits(40,.5,3);self.assertTrue(r['small_sample']);self.assertTrue(r['not_statistical_significance']);self.assertTrue(r['not_net_profit'])
if __name__=='__main__':unittest.main()
