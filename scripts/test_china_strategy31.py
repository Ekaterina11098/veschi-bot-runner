import unittest
from china_strategy import review,TARGET_DRR_PCT
def check(spend=3,orders=0,amount=0,pre=20,old=50,minimum=28,dates=('2026-10-30',),verified=True,remaining=None,exception=False):
 return review(dict(spend=spend,orders=orders,amount=amount,clicks=10),dict(available=True,pre_ad_per_order_cny=pre),dict(payment_type='cpc',currency='CNY',bid_minor=old,minimum_minor=minimum,step_minor=1),dates,verified,remaining,exception)
class Strategy(unittest.TestCase):
 def test_target_is_common_five(self):self.assertEqual(TARGET_DRR_PCT,5)
 def test_five_is_boundary_not_guarantee(self):self.assertFalse(check(5,1,100)['requires_review']);self.assertTrue(check(5.01,1,100)['requires_review'])
 def test_zero_orders_never_zero_drr(self):
  r=check();self.assertIsNone(r['drr_pct']);self.assertEqual(r['action'],'lower_bid_recommendation');self.assertEqual(r['target_minor'],28)
 def test_at_minimum_consider_exclusion(self):self.assertEqual(check(old=28)['action'],'exclude_sku_recommendation')
 def test_negative_or_zero_economy_exclusion(self):
  for pre in [-1,0]:self.assertEqual(check(pre=pre)['action'],'exclude_sku_recommendation')
 def test_small_sample_does_not_allow_endless_spend(self):self.assertIsNotNone(check(spend=.1)['action'])
 def test_no_spend_no_waste_recommendation(self):self.assertFalse(check(spend=0)['requires_review'])
 def test_today_or_change_day_not_action(self):self.assertIsNone(check(dates=())['action']);self.assertEqual(check(dates=())['status'],'await_completed_day')
 def test_stale_or_missing_inputs_not_action(self):self.assertIsNone(check(verified=False)['action'])
 def test_unknown_costs_not_profit(self):self.assertEqual(check(pre=None)['status'],'verify_economics')
 def test_approved_bounded_test_can_continue(self):self.assertEqual(check(remaining=2)['status'],'approved_bounded_test')
 def test_exhausted_budget_no_continuation(self):self.assertEqual(check(remaining=0)['action'],'lower_bid_recommendation')
 def test_high_drr_needs_explicit_exception_even_if_profitable(self):self.assertEqual(check(6,1,100,remaining=10)['action'],'lower_bid_recommendation');self.assertEqual(check(6,1,100,remaining=10,exception=True)['status'],'approved_bounded_test')
 def test_positive_economics_does_not_raise_common_target(self):self.assertEqual(check(6,1,100,pre=1000)['action'],'lower_bid_recommendation')
 def test_unknown_orders_no_zero_substitution(self):self.assertEqual(check(orders=None)['status'],'unknown_counters')
 def test_unknown_minimum_never_invent_bid(self):self.assertIsNone(check(minimum=None)['action']);self.assertEqual(check(minimum=None)['status'],'verify_bid_limits')
 def test_no_execution_permission(self):
  for r in [check(),check(old=28),check(remaining=2)]:self.assertFalse(r['execution_authorized']);self.assertEqual(r['wb_writes'],0)

class DiagnosticIntegration(unittest.TestCase):
 def fact(self):
  from datetime import datetime,timezone
  self.now=datetime(2026,10,31,20,tzinfo=timezone.utc);at=self.now.isoformat()
  return dict(nm_id=143,article='143-bag',history_checked=True,gaps=[],changes=[],
   stock=dict(observed_at=at,available=10,cogs_cny=50),price=dict(observed_at=at,currency='CNY',seller_cny=500),
   campaign=dict(observed_at=at,id=40000001,status=9,currency='CNY',payment_type='cpc',placement='recommendations',bid_minor=50,minimum_minor=28,step_minor=1,maximum_minor=500,budget_cny=100),
   quality={},visibility={},economy=dict(observed_at=at,completed_sample=10,buyout=.8,commission_pct=20,logistics_cny=10,tax_pct=5,handling_cny=1),
   daily=[dict(date=d,views=100,clicks=10,baskets=0,orders=0,spend=3,amount=0) for d in ['2026-10-28','2026-10-29','2026-10-30']])
 def test_real_diagnostic_gives_lower_proposal_even_when_public_card_unavailable(self):
  from china_article_diagnostic import evaluate,render
  f=self.fact();r=evaluate(f,self.now)
  self.assertEqual(r['action']['kind'],'lower_bid_recommendation');self.assertEqual(r['action']['target_minor'],28)
  text=render(dict(rows=[r],period_from=r['period_from'],period_to=r['period_to']))
  self.assertIn('не определена:0 заказов',text);self.assertIn('потолок5%',text);self.assertFalse(r['execution_authorized'])
 def test_minimum_bid_yields_exclusion_proposal(self):
  from china_article_diagnostic import evaluate
  f=self.fact();f['campaign']['bid_minor']=28;self.assertEqual(evaluate(f,self.now)['action']['kind'],'exclude_sku_recommendation')
 def test_change_day_excluded(self):
  from china_article_diagnostic import evaluate
  f=self.fact();f['changes']=[dict(verified=True,kind='bid',at=self.now.isoformat())]
  self.assertIsNone(evaluate(f,self.now)['action'])
 def test_missing_cost_never_recommends_invented_bid(self):
  from china_article_diagnostic import evaluate
  f=self.fact();f['stock']['cogs_cny']=None;self.assertIsNone(evaluate(f,self.now)['action'])
 def test_own_true_zero_buyout_is_economic_risk_not_unknown_or_fifty(self):
  from china_article_diagnostic import evaluate
  f=self.fact();f['economy']['buyout']=0;r=evaluate(f,self.now)
  self.assertEqual(r['economics']['buyout'],0);self.assertEqual(r['action']['kind'],'exclude_sku_recommendation')
if __name__=='__main__':unittest.main()

