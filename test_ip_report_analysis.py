import copy,sys,types,unittest
from unittest.mock import patch
try:import requests
except ImportError:sys.modules['requests']=types.SimpleNamespace(post=lambda *a,**kw:None)
from ip_report_analysis import financial_result,economics,screen,review_report,validate,Halt,ROOT
from test_ip_cloud_dialog import FakeState
DAY='2026-11-05'
def fixture():
 own=[dict(p_id=1,nm_id=101,sa_name='101-Bag-black',subject_id=50,orders_count=3,orders_sum=3000,stock_api_stock_count=30,fbs_stock=0,profit=99999)]
 inp=dict(period=DAY,own=own,finance={},models={'101':{'historical_order_price':1000,'scenario_one_buyout_after_assumed_5pct_ad':200,'period_to':'2026-11-01','not_current_period_profit':True}},gaps=[])
 a=dict(nm=101,sku='101-Bag-black',campaign=1,kind='raise_bid',stored_bid_minor=295,target_bid_minor=309,daily={DAY:dict(spend=20,orders=3,revenue=3000,clicks=10,views=100)},criterion='Проверка',baseline={})
 c=dict(actions=[a],review_coverage={'own_articles':1,'existing_pairs':1})
 v=dict(period=DAY,campaigns=[dict(campaign_id=1,spend=100,budget=dict(valid=True,today_observation=True,balance=5000,observed_at='2026-11-06T04:30:00Z'),sku_rows=[])])
 return inp,c,v
class AnalysisTests(unittest.TestCase):
 def test_ip_tax_and_no_second_ad_deduction(self):
  v=dict(period_from=DAY,period_to=DAY,cabinet='token_2',currency='RUB',for_pay=700,seller_sales=1000,seller_returns=-200,net_units=1,own_unit_cost=100,financial_ads=50,for_pay_includes_ads=True,expenses_reconciled=True,own_cost_source='saved-own-cost')
  r=financial_result(v,DAY);self.assertEqual(r['tax_reserve'],120);self.assertEqual(r['after_ads'],480);self.assertEqual(r['before_ads'],530)
  for key,value in [('currency','CNY'),('cabinet','token_3'),('tax_reserve_rate',.05),('expenses_reconciled',False),('period_to','2026-11-04')]:
   other=dict(v,**{key:value});self.assertEqual(financial_result(other,DAY)['status'],'unknown')
 def test_unknown_is_not_zero_or_mpstats_profit(self):
  inp,_,_=fixture();r=economics(inp)['101'];self.assertIsNone(r['profit_after_ads']);self.assertIsNone(r['buyout_probability']);self.assertTrue(r['conditional_model']['not_current_period_profit'])
 def test_period_profit_not_reused_and_zero_is_known(self):
  inp,_,_=fixture();inp['finance']['101']=dict(status='preliminary',period_from=DAY,period_to='2026-11-04',after_ads=500,all_channels=True,campaign_profit=False)
  self.assertIsNone(economics(inp)['101']['profit_after_ads']);inp['finance']['101'].update(period_to=DAY,after_ads=0);self.assertEqual(economics(inp)['101']['profit_after_ads'],0)
 def test_best_growth_placement_per_sku_and_no_caps(self):
  inp,c,v=fixture();second=copy.deepcopy(c['actions'][0]);second['campaign']=2;second['daily'][DAY]['orders']=1;c['actions'].append(second);v['campaigns'].append(dict(v['campaigns'][0],campaign_id=2))
  a,audit=screen(c,v,inp);self.assertEqual(len(a),1);self.assertEqual(a[0]['campaign'],1);self.assertTrue(a[0]['growth_reserve']['not_daily_cap']);self.assertFalse(audit['rules']['msk50_required'])
 def test_no_reserve_no_ready_growth_and_no_automatic_topup(self):
  inp,c,v=fixture();v['campaigns'][0]['budget']['balance']=1;a,audit=screen(c,v,inp);self.assertEqual(a,[]);self.assertTrue(audit['research'])
 def test_fbo_only_no_fbs_future_supply(self):
  inp,c,v=fixture();inp['own'][0].update(subject_id=51,stock_api_stock_count=0,fbs_stock=1000);a,_=screen(c,v,inp);self.assertEqual(a,[])
 def test_isolated_high_ratio_is_not_persistent(self):
  inp,c,v=fixture();a=c['actions'][0];a['kind']='lower_bid';a['daily']={DAY:dict(spend=10,orders=1,revenue=100), '2026-11-04':dict(spend=1,orders=10,revenue=1000)};result,audit=screen(c,v,inp);self.assertEqual(result,[]);self.assertTrue(audit['rejected'])
 def test_marginal_economics_uses_ip_stress_cost(self):
  inp,c,v=fixture();inp['marginal_models']={'101':dict(cabinet='token_2',currency='RUB',tax_reserve_rate=.15,period_to=DAY,verified=True,expected_margin_before_ads=5,stress_margin_before_ads=5)};a,_=screen(c,v,inp);self.assertEqual(a,[])
 def test_sol_cannot_invent_action(self):
  r=dict(selected=['invented'],directions={k:'checked'for k in('raise','add','reduce','exclude')},research=[],summary='')
  with self.assertRaises(Halt):validate(r,{},set())
 def test_cached_review_no_second_model_and_original_action_parameters(self):
  inp,c,v=fixture();state=FakeState();state.data[ROOT+'policy']['report_review_enabled']=True
  class Store:
   def cache_set(self,*a,**kw):pass
  calls=[]
  def model(s,identity,data):calls.append(data);return dict(selected=[data['allowed_actions'][0]['id']],directions={k:'checked'for k in('raise','add','reduce','exclude')},research=[],summary='Saved data reviewed'),dict(model='gpt-6.1-sol',charged_micro_usd=1000,model_calls=1)
  with patch('ip_report_analysis.State',return_value=state),patch('ip_report_analysis.load_inputs',return_value=inp):
   a=review_report(Store(),v,c,model);b=review_report(Store(),v,c,model)
  self.assertEqual(len(calls),1);self.assertEqual(b['sol_analysis']['model_calls_this_run'],0);self.assertEqual(a['actions'][0]['target_bid_minor'],309)
  self.assertNotIn('baseline',calls[0]['allowed_actions'][0]);self.assertNotIn('own',calls[0])
 def test_uncertain_model_is_not_replayed(self):
  inp,c,v=fixture();state=FakeState();state.data[ROOT+'policy']['report_review_enabled']=True
  with patch('ip_report_analysis.State',return_value=state),patch('ip_report_analysis.load_inputs',return_value=inp):
   def fail(*a):raise TimeoutError('unknown')
   with self.assertRaises(TimeoutError):review_report(None,v,c,fail)
   with self.assertRaises(Halt):review_report(None,v,c,lambda *a:self.fail('repeated'))
 def test_monthly_stop_keeps_figures_and_no_unreviewed_commands(self):
  inp,c,v=fixture();state=FakeState();state.data[ROOT+'policy']['report_review_enabled']=True
  with patch('ip_report_analysis.State',return_value=state),patch('ip_report_analysis.load_inputs',return_value=inp):
   def stop(*a):raise Halt('Paid budget limit reached')
   result=review_report(None,v,c,stop)
   self.assertEqual(result['actions'],[]);self.assertEqual(result['sol_analysis']['model_calls_this_run'],0);self.assertIn('месячный',result['analysis_notice'])
   result=review_report(None,v,c,lambda *a:self.fail('repeat'))
   self.assertEqual(result['actions'],[])
 def test_changed_evidence_does_not_expand_prior_sol_selection(self):
  inp,c,v=fixture();state=FakeState();state.data[ROOT+'policy']['report_review_enabled']=True
  class Store:
   def cache_set(self,*a,**kw):pass
  def model(s,identity,data):return dict(selected=[data['allowed_actions'][0]['id']],directions={k:'checked'for k in('raise','add','reduce','exclude')},research=[],summary='reviewed'),dict(model='gpt-6.1-sol',model_calls=1)
  with patch('ip_report_analysis.State',return_value=state),patch('ip_report_analysis.load_inputs',return_value=inp):
   review_report(Store(),v,c,model);c['actions'][0]['target_bid_minor']=308
   result=review_report(Store(),v,c,lambda *a:self.fail('repeat'))
   self.assertEqual(result['actions'],[])
 def test_global_concurrency_includes_report_and_dialog(self):
  from ip_cloud_dialog import Budget
  s=FakeState();b=Budget(s);b.reserve('report:'+DAY)
  with self.assertRaises(Halt):b.reserve(51)
  b.settle('report:'+DAY,dict(input_tokens=100,output_tokens=10));b.reserve(51)
if __name__=='__main__':unittest.main()
