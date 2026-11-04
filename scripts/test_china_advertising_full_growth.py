import copy,json,unittest
from unittest.mock import patch
from pathlib import Path
from china_advertising_full_growth import proposed_actions,addition_actions
class FullCabinetGrowthTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  path=Path(__file__).with_name('full-growth-fixture.json')
  if not path.exists():raise unittest.SkipTest('Private recorded fixture is exercised by the read-only cloud verifier')
  cls.fixture=json.loads(path.read_text(encoding='utf-8'))
 def source(self):
  x=copy.deepcopy(self.fixture)
  return dict(period_to=x['period_to'],executions=[],batches=x['batches'],full_growth_inputs=x['v']),x['changes']
 def evaluate(self,s,changes):
  with patch('china_advertising_v2.history',return_value=changes):return proposed_actions(s)
 def test_full_recorded_scope_and_eight_proposals(self):
  s,ch=self.source();a,u=self.evaluate(s,ch)
  self.assertEqual(len(s['full_growth_inputs']['screened_nm_ids']),312)
  self.assertEqual(len(a),8)
  self.assertFalse({x['nm_id']for x in a}&{1473245494,1473245510,1473244000})
  self.assertEqual(len({x['nm_id']for x in a}),len(a))
 def test_verified_changes_exclude_changed_day(self):
  s,ch=self.source();a,_=self.evaluate(s,ch)
  ch.extend(dict(nm=x['nm_id'],cid=x['campaign_id'],kind='bid',at='2026-11-03T15:00:00+00:00')for x in a)
  later,_=self.evaluate(s,ch)
  self.assertFalse({x['nm_id']for x in later}&{x['nm_id']for x in a})
 def test_unknown_published_stock_never_becomes_ready(self):
  s,ch=self.source()
  for e in s['full_growth_inputs']['economics']['rows'].values():e['published_stock']=None
  a,_=self.evaluate(s,ch);self.assertEqual(a,[])
 def test_three_day_reserve_required_without_auto_funding(self):
  s,ch=self.source()
  for row in s['full_growth_inputs']['budgets']['adverts']:row['total']=0
  a,u=self.evaluate(s,ch);self.assertEqual(a,[]);self.assertTrue(u)
 def test_exact_quote_is_required(self):
  s,ch=self.source();s['full_growth_inputs']['minimums']={}
  a,_=self.evaluate(s,ch);self.assertEqual(a,[])
 def test_nonpositive_own_economics_not_rescued_by_low_drr(self):
  s,ch=self.source()
  for e in s['full_growth_inputs']['economics']['rows'].values():e['expected_margin_before_ads_cny']=-1
  a,_=self.evaluate(s,ch);self.assertEqual(a,[])
 def test_empty_addition_scan_does_not_invent_proposals(self):
  s,_=self.source();self.assertEqual(addition_actions(s,[]),[])
class StagedCollectionTests(unittest.TestCase):
 def fake(self):
  from datetime import datetime,timezone
  now=datetime.now(timezone.utc).isoformat()
  state=dict(own=dict(rows=[],observed_at=now,period_from='2026-10-05',period_to='2026-11-03'),published_stock=dict(amounts={'1':5,'999':5},missing_nm_ids=[],observed_at=now),fx=dict(rub_per_cny=12.1816),economics=dict(rows={},missing={},observed_at=now),campaigns=[],budgets=dict(adverts=[]),config=dict(currency='CNY',cpcStep=1,cpcMaxBid=1290),minimums={})
  class IO:
   def __init__(self):self.data={'china_agent:advertising_full_growth:2026-11-04:v1:inputs':state};self.calls=0;self.fail=False
   def get(self,k):
    if k=='china_agent:advertising_format:v2':return dict(growth_excluded_nm_ids=[])
    return copy.deepcopy(self.data.get(k))
   def put(self,k,v):self.data[k]=copy.deepcopy(v)
   def create(self,k,v):
    if k in self.data:return False
    self.put(k,v);return True
   def wb(self,path):
    self.calls+=1
    if self.fail:raise RuntimeError('Temporary read failure')
    return dict(listGoods=[dict(nmID=nm,vendorCode=article,currencyIsoCode4217='CNY',sizes=[dict(discountedPrice=100,sizeID=nm)])for nm,article in[(1,'one'),(999,'new')]])
  s=dict(catalogue=dict(rows=[dict(nmID=1,vendorCode='one')]),executions=[])
  return IO(),s,now
 def imports(self):
  import types,contextlib
  return patch.dict('sys.modules',{'china_analytic_dialog':types.SimpleNamespace(Analyst=object,reading=contextlib.nullcontext),'china_intraday_analysis':types.SimpleNamespace(rate=lambda *a:None)})
 def test_new_wb_catalogue_items_are_screened_and_stages_reused(self):
  from china_advertising_full_growth import collect
  io,s,now=self.fake();stock=dict(rows=[],missing_articles=[],coverage_complete=True,observed_at=now)
  with self.imports(),patch('china_moysklad_read.read_stock',return_value=stock)as reader:
   first=collect(io,s,'2026-11-04');second=collect(io,s,'2026-11-04')
  self.assertEqual(first['full_growth_review']['catalogue_count'],2)
  self.assertEqual(first['full_growth_inputs']['screened_nm_ids'],[1,999])
  self.assertEqual(io.calls,1);self.assertEqual(reader.call_count,1)
 def test_read_failure_preserves_stages_for_next_attempt(self):
  from china_advertising_full_growth import collect
  from china_morning_readiness import PendingAdvertisingDay
  io,s,now=self.fake();io.fail=True
  with self.imports(),patch('china_moysklad_read.read_stock',return_value=dict(rows=[],missing_articles=[],coverage_complete=True,observed_at=now))as reader:
   with self.assertRaises(PendingAdvertisingDay):collect(io,s,'2026-11-04')
   self.assertIn('own',io.get('china_agent:advertising_full_growth:2026-11-04:v1:inputs'))
   io.fail=False;result=collect(io,s,'2026-11-04')
  self.assertEqual(result['full_growth_review']['status'],'complete');self.assertEqual(reader.call_count,1)

if __name__=='__main__':unittest.main()
