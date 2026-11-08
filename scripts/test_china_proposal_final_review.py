import copy,unittest
from unittest.mock import patch
from china_proposal_final_review import complete

class IO:
 def __init__(self):
  self.values={};self.full=dict(cabinet='token_3',status='complete',economics=dict(rows={'1':dict(sample_size=10,buyout=.8,buyout_fallback=False,stock_free=10,seller_price_cny=200,own_cogs_rub=100,logistics_cny=10,logistics_historical=True,fx_rub_per_cny=12,commission_pct=20,tax_pct=5,expected_margin_before_ads_cny=100),'3':dict(stock_free=0,model_unavailable='No available MSK stock')}),own=dict(rows=[dict(nm_id=1,backwardlogisticsum=0,average_delivery_cost=0)]))
 def get(self,k):return self.full if k.startswith('china_agent:advertising_full_growth:')else self.values.get(k)
 def db(self,path):return []
 def put(self,k,v):self.values[k]=v
 def create(self,k,v):self.values[k]=v;return True

def source():
 return dict(observed_at='2026-11-08T05:25:00+00:00',period_to='2026-11-07',products=[dict(nm_id=n,sa_name='Bag'+str(n),subject_id=50,finished_orders=10,is_payed=8,open_card_count=100,funnel_orders_count=5,advertisement=0)for n in(1,2,3)],prices=[dict(nmID=n,sizes=[dict(discountedPrice=200)])for n in(1,2,3)],stock=[dict(article='Bag1',stock=10,reserve=0,price=10000)],policy=dict(logistics_by_nm={}),campaigns={'9':dict(status=9,nm_settings=[dict(nm_id=2)])},experience=dict(experiences=[],recent_changed_nm_ids=[]),protected=[])
def candidate():
 return dict(nm_id=1,article='Bag1',subject_id=50,price_cny=200,stock=10,paid=8,finished=10,conversion=5,recent_orders=1,group='orders',requires_review=[])
def post():
 return dict(source_key='complete-day-20261107',rows=[dict(nm_id=1,open_card_count=100,funnel_orders_count=5)])
class FinalReviewTests(unittest.TestCase):
 def test_every_scoped_sku_receives_terminal_decision_before_offer(self):
  io=IO()
  with patch('china_proposal_final_review.assess',return_value=[candidate()]),patch('china_proposal_final_review.period',return_value=post()):
   s,g,a,k=complete(io,source(),dict(job_id=1,revision='test',subject_ids=[50]))
  self.assertEqual(a['scope_count'],3);self.assertEqual(a['counts'],dict(ready=1,out_of_scope=1,rejected=1));self.assertTrue(a['all_scope_accounted'])
  self.assertEqual(len(g['orders']),1);self.assertTrue(g['orders'][0]['full_checks_completed'])
  self.assertIn('1',s['policy']['logistics_by_nm'])
 def test_missing_reverse_cost_blocks_entire_offer_instead_of_partial_result(self):
  io=IO();io.full['own']['rows'][0].pop('backwardlogisticsum')
  with patch('china_proposal_final_review.assess',return_value=[candidate()]),patch('china_proposal_final_review.period',return_value=post()),self.assertRaisesRegex(ValueError,'заблокирован'):
   complete(io,source(),dict(job_id=1,revision='test'))
  saved=next(iter(io.values.values()));self.assertEqual(saved['status'],'blocked');self.assertEqual(saved['blocked_nm_ids'],[1])
 def test_absent_completed_day_never_falls_back_to_today_or_review_table(self):
  with patch('china_proposal_final_review.period',return_value=None),patch('china_proposal_final_review.assess',return_value=[candidate()]),self.assertRaisesRegex(ValueError,'полного среза'):
   complete(IO(),source(),dict(job_id=1))
 def test_same_day_verified_content_change_defers_candidate(self):
  io=IO();io.db=lambda path:[dict(cache_key='china_agent:description_append:v2:verified:1',payload=dict(verified_at='2026-11-07T12:00:00Z'))]
  with patch('china_proposal_final_review.assess',return_value=[candidate()]),patch('china_proposal_final_review.period',return_value=post()):
   _,g,a,_=complete(io,source(),dict(job_id=1))
  self.assertEqual(a['ledger'][0]['status'],'deferred');self.assertFalse(g['orders'])
 def test_known_future_experiment_window_is_terminal_defer_not_missing_data(self):
  r=candidate();r['requires_review']=['Недавнее изменение']
  s=source();s['experience']['experiences']=[dict(started_at='2026-11-05T12:00:00Z',action=dict(nm_ids=[1]),comparison=dict(evaluate_from='2026-11-09'))]
  with patch('china_proposal_final_review.assess',return_value=[r]),patch('china_proposal_final_review.period',return_value=post()):
   _,g,a,_=complete(IO(),s,dict(job_id=1))
  self.assertEqual(a['counts']['deferred'],1);self.assertEqual(a['ledger'][0]['eligible_after_msk'],'2026-11-09');self.assertFalse(g['orders'])
if __name__=='__main__':unittest.main()
