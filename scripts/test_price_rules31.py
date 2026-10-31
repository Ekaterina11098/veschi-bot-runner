import ast, copy, importlib.util, pathlib, unittest
from datetime import date, datetime, timedelta, timezone
ROOT=pathlib.Path(__file__).parent
def module(name):
 spec=importlib.util.spec_from_file_location(name, ROOT/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
result=module('china_price_experiment_result');brief=module('china_price_brief')
economics=module('china_price_economic_target')
def pure_function(file,name,scope):
 tree=ast.parse((ROOT/file).read_text(encoding='utf-8'));node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
 exec(compile(ast.Module(body=[node],type_ignores=[]),file,'exec'),scope);return scope[name]
tracked=pure_function('china_morning_pair.py','tracked_rows',dict(datetime=datetime,timedelta=timedelta,MSK=timezone(timedelta(hours=3))))
windows=pure_function('china_daily_expected_control.py','comparison_windows',dict(timedelta=timedelta))
DAY=date(2026,11,1)
CAT=dict(cabinet='token_3',rows=[dict(vendorCode='143-ReginaBag-black',nmID=1473245494,currencyIsoCode4217='CNY',discount=45,sizes=[dict(price=901,discountedPrice=495.55)])])
def review(days=1):
 return dict(report_date=str(DAY),status='complete_disclosed_forecast_model',model_version='wb_profit_floor_price_hypothesis_v4',products=[dict(article='143-ReginaBag-black',before_price=450.5,after_price=495.55,full_days=days,buyout_fallback=False,buyout_sample=94,result=dict(status='rollback_review',early_review_criteria_met=True),economic_target=dict(basis='profit_floor_demand_hypothesis',status='recommended',price_cny=450.5,base_cny=901,discount=50,expected_profit_advantage_per_day=100))])
class PriceRules(unittest.TestCase):
 def test_baseline_does_not_mix_previous_prices(self):
  pair=windows(date(2026,10,30),DAY)
  from decimal import Decimal
  history={'143':[dict(day=date(2026,10,28),price_cny=Decimal('450.5'))]}
  p=economics.baseline_after_last_change(pair,'143',450.5,date(2026,10,30),history)
  self.assertEqual(p[0],(date(2026,10,29),date(2026,10,29)))
 def target(self,floor=2040,**kwargs):
  old=dict(current_cny=400,base_cny=800,discount=50);new=dict(current_cny=500,base_cny=1000,discount=50)
  before=dict(expected_profit_per_day=floor,orders_per_day=10*(400/500)**-3,views=1000,days=1)
  after=dict(advertising_per_day=0,orders_per_day=10,views=1000,days=1)
  before.update(kwargs.pop('before',{}));after.update(kwargs.pop('after',{}))
  return economics.choose_target(old,new,before,after,buyout_probability=1,retention=1,cost=300,dispatch=0,fx=1)
 def test_economic_price_can_be_intermediate(self):
  t=self.target();self.assertEqual(t['status'],'recommended');self.assertGreater(t['price_cny'],400);self.assertLess(t['price_cny'],500)
  self.assertGreaterEqual(t['predicted_profit_per_day'],2040);self.assertGreaterEqual(t['predicted_orders_per_day'],t['required_orders_per_day']);self.assertFalse(t['execution_authorized'])
 def test_old_price_is_a_hard_floor(self):
  self.assertTrue(all(400<=p['price_cny']<500 for p in economics.feasible_prices(dict(current_cny=400,base_cny=800,discount=50),dict(current_cny=500,base_cny=1000,discount=50))))
 def test_unreachable_profit_is_not_faked(self):
  self.assertEqual(self.target(10000)['status'],'profit_floor_not_reached')
 def test_demand_hypothesis_requires_compatible_traffic(self):
  self.assertEqual(self.target(before=dict(views=None))['status'],'incomplete_economic_inputs')
 def test_no_demand_recovery_is_not_faked(self):
  self.assertEqual(self.target(before=dict(orders_per_day=5))['status'],'no_supported_demand_recovery')
 def test_recommended_target_never_below_previous(self):
  r=review();r['products'][0]['economic_target']['price_cny']=440
  with self.assertRaises(RuntimeError):brief.lowering(r,DAY,CAT)
 def test_strong_one_full_day_can_recommend(self):
  r=result.experiment_result(1000,400,1000,50,1000,10,1,94);self.assertEqual(r['status'],'rollback_review');self.assertFalse(r['execution_authorized'])
 def test_incomplete_day_cannot_recommend(self):
  self.assertNotEqual(result.experiment_result(1000,400,1000,50,1000,10,0,94)['status'],'rollback_review')
 def test_small_sample_cannot_recommend_early(self):
  self.assertNotEqual(result.experiment_result(1000,400,20,2,20,0,1,94)['status'],'rollback_review')
 def test_unknown_profit_blocks(self):
  self.assertEqual(result.experiment_result(None,None,1000,50,1000,10,1,94)['status'],'incomplete')
 def test_unresolved_buyout_blocks_early(self):
  self.assertNotEqual(result.experiment_result(1000,400,1000,50,1000,10,1,0)['status'],'rollback_review')
 def test_profit_decline_without_cr_decline_after_four_days(self):
  self.assertEqual(result.experiment_result(1000,700,1000,30,1000,30,4,94)['status'],'rollback_review')
 def test_profit_decline_without_funnel_after_four_days(self):
  self.assertEqual(result.experiment_result(1000,700,None,None,None,None,4,94)['status'],'rollback_review')
 def test_cr_drop_but_profit_growth_does_not_lower(self):
  self.assertEqual(result.experiment_result(1000,1200,1000,50,1000,10,1,94)['status'],'mixed')
 def test_exact_previous_price_not_fixed_minus_five(self):
  self.assertEqual(brief.lowering(review(),DAY,CAT),[('143-ReginaBag-black','495,55','450,5')])
 def test_unsubstantiated_target_is_omitted(self):
  r=review();del r['products'][0]['economic_target'];self.assertEqual(brief.lowering(r,DAY,CAT),[])
 def test_below_profit_floor_is_omitted(self):
  r=review();r['products'][0]['economic_target']['expected_profit_advantage_per_day']=-1;self.assertEqual(brief.lowering(r,DAY,CAT),[])
 def test_changed_current_price_does_not_repeat(self):
  c=copy.deepcopy(CAT);c['rows'][0]['sizes'][0]['discountedPrice']=450.5;self.assertEqual(brief.lowering(review(),DAY,c),[])
 def test_stale_review_is_not_current(self):
  self.assertIsNone(brief.lowering(review(),date(2026,11,2),CAT))
 def test_default_buyout_cannot_produce_target(self):
  r=review();r['products'][0]['buyout_fallback']=True;self.assertEqual(brief.lowering(r,DAY,CAT),[])
 def test_zero_full_days_rejected(self):
  with self.assertRaises(RuntimeError):brief.lowering(review(0),DAY,CAT)
 def test_early_evidence_required(self):
  r=review();r['products'][0]['result']['early_review_criteria_met']=False
  with self.assertRaises(RuntimeError):brief.lowering(r,DAY,CAT)
 def test_pending_cohort_survives_first_check(self):
  state=dict(price_history={'143':dict(article='143',last_price_change=dict(detected_at='2026-10-30T18:19:28+03:00'))})
  self.assertEqual(len(tracked(state,date(2026,11,10))),1)
  state['price_review_progress']={'143':dict(detected_at='2026-10-30T18:19:28+03:00',complete=True)}
  self.assertEqual(tracked(state,date(2026,11,10)),[])
 def test_new_change_resets_progress(self):
  s=dict(price_history={'143':dict(last_price_change=dict(detected_at='2026-11-01T18:00:00+03:00'))},price_review_progress={'143':dict(detected_at='2026-10-30T18:19:28+03:00',complete=True)})
  self.assertEqual(len(tracked(s,date(2026,11,10))),1)
 def test_first_full_day_only_next_day(self):
  self.assertIsNone(windows(date(2026,10,30),date(2026,10,31)))
  self.assertEqual(windows(date(2026,10,30),DAY)[1],(date(2026,10,31),date(2026,10,31)))
 def test_pending_window_remains_fresh(self):
  self.assertEqual(windows(date(2026,10,30),date(2026,11,10))[1],(date(2026,11,6),date(2026,11,9)))
if __name__=='__main__':unittest.main()

