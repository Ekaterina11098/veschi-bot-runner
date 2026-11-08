import copy,unittest,sys,types,os
from unittest.mock import patch,Mock
import china_ad_retest as r
from china_ad_candidate_review import build,deliver_review,ROOT

def source():
 return dict(observed_at='2026-11-08T05:25:00+00:00',period_from='2026-10-09',period_to='2026-11-07',memory_used=True,
  experience=dict(experiences=[],recent_changed_nm_ids=[]),campaigns={},protected=[1],published_stock={'1':20},
  prices=[dict(nmID=1,sizes=[dict(discountedPrice=200)])],stock=[dict(article='bag',stock=50,reserve=2,price=10000)],
  orders=[dict(nmId=1)],products=[dict(nm_id=1,sa_name='bag',finished_orders=6,is_payed=4,open_card_count=1000,funnel_orders_count=20,
   price_after_spp=1000,price_after_discount=1200,advertisement=500,subject_id=50)],
  policy=dict(logistics_by_nm={'1':dict(delivery_cny=10)},category_minimum_minor={'50':28}))
def improved():
 event=dict(event_id='event',started_at='2026-10-20T10:00:00+00:00')
 b=dict(period_from='2026-10-16',period_to='2026-10-19',row=dict(open_card_count=200,funnel_orders_count=1),source=11)
 a=dict(period_from='2026-11-04',period_to='2026-11-07',row=dict(open_card_count=200,funnel_orders_count=5),source=12)
 return r.compare(event,b,a,'2026-11-07')
class Retests(unittest.TestCase):
 def test_missing_period_uses_insert_before_update_and_never_model(self):
  class IO:
   def __init__(self):self.mem={}
   def db(self,*a):return []
   def get(self,k):return self.mem.get(k)
   def create(self,k,v):self.mem[k]=v;return True
   def put(self,k,v):
    if k not in self.mem:raise RuntimeError('State readback mismatch')
    self.mem[k]=v
  io=IO()
  mods={'analytics.mpstats_probe':types.SimpleNamespace(discover=lambda *a,**kw:None),
        'analytics.mpstats_gaps':types.SimpleNamespace(execute_reads=lambda *a,**kw:None)}
  with patch.dict(sys.modules,mods),patch.dict(os.environ,MPSTATS_API_TOKEN='fixture'):
   self.assertIsNone(r.period(io,'2026-11-04','2026-11-07',collect=True))
  self.assertEqual(next(iter(io.mem.values()))['status'],'unavailable')
 def test_old_ad_spend_and_exclusion_are_not_permanent_bans(self):
  s=source();s['retest_evidence']={'1':improved()}
  rows=r.assess(s);self.assertEqual(len(rows),1);self.assertTrue(rows[0]['eligible'])
 def test_missing_history_is_research_not_zero_candidates(self):
  s=source();rows=r.assess(s)
  self.assertEqual(len(rows),1);self.assertFalse(rows[0]['eligible'])
  self.assertEqual(build(s)['total'],1)
 def test_recent_change_and_explicit_hold_remain_blocked(self):
  s=source();s['retest_evidence']={'1':improved()};s['experience']['recent_changed_nm_ids']=[1]
  self.assertFalse(r.assess(s)[0]['eligible'])
  s=source();s['products'][0]['nm_id']=1007948808;s['prices'][0]['nmID']=1007948808;s['policy']['logistics_by_nm']={'1007948808':{'delivery_cny':10}}
  self.assertIn('Отдельный запрет владельца',r.assess(s)[0]['requires_review'])
 def test_msk_free_stock_is_availability_basis(self):
  s=source();s['retest_evidence']={'1':improved()};s.pop('published_stock')
  self.assertTrue(r.assess(s)[0]['eligible']);self.assertEqual(build(s)['improved'],1)
  s['stock'][0]['reserve']=s['stock'][0]['stock'];self.assertEqual(r.assess(s),[])
 def test_exact_counts_and_equal_full_windows(self):
  e=improved();self.assertEqual(e['status'],'improved');self.assertAlmostEqual(e['before']['cr_pct'],.5)
  self.assertAlmostEqual(e['after']['cr_pct'],2.5);self.assertAlmostEqual(e['delta_pp'],2)
  self.assertEqual(e['causality'],'not_established')
 def test_change_day_and_moscow_midnight_are_excluded(self):
  event=dict(event_id='x',started_at='2026-10-20T23:30:00+00:00')
  self.assertEqual(str(r.changed_day(event)),'2026-10-21')
  b=dict(period_from='2026-10-17',period_to='2026-10-20',row=dict(open_card_count=200,funnel_orders_count=1))
  a=dict(period_from='2026-10-21',period_to='2026-10-24',row=dict(open_card_count=200,funnel_orders_count=5))
  self.assertEqual(r.compare(event,b,a,'2026-10-24')['status'],'invalid_period')
 def test_small_sample_or_stale_period_does_not_approve_retest(self):
  e=improved();e['fresh_complete']=False;s=source();s['retest_evidence']={'1':e}
  self.assertFalse(r.assess(s)[0]['eligible'])
 def test_review_delivery_never_creates_plan_or_approval_and_deduplicates(self):
  s=source()
  class IO:
   bot='fixture'
   def __init__(self):self.mem={}
   def get(self,k):return self.mem.get(k)
   def create(self,k,v):
    if k in self.mem:return False
    self.mem[k]=copy.deepcopy(v);return True
   def put(self,k,v):self.mem[k]=copy.deepcopy(v)
   def tg(self,*a):return {'id':8780468043}
  io=IO();req=dict(job_id=268,reply_message_id=777)
  response=Mock();response.json.return_value=dict(ok=True,result=dict(chat={'id':-1004342917488},message_id=900))
  send=Mock(return_value=response)
  with patch('china_table_png.render',return_value=[b'fixture']),patch.dict(sys.modules,{'requests':types.SimpleNamespace(post=send)}):
   value=deliver_review(io,req,s);deliver_review(io,req,s)
  self.assertEqual(send.call_count,1);self.assertEqual(value['total'],1)
  self.assertTrue(all(k.startswith(ROOT) for k in io.mem))
  self.assertFalse(value['execution_authorized'])
if __name__=='__main__':unittest.main()
