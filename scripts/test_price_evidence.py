import sys, types, unittest, importlib.util, pathlib
from datetime import date
from unittest.mock import patch
from china_price_evidence import valid_daily_orders, cached_order_products, price_evidence

class EvidenceTests(unittest.TestCase):
 def test_totals_do_not_prove_daily_history(self):
  self.assertFalse(valid_daily_orders(dict(orders_count=4),4))
  self.assertFalse(valid_daily_orders(dict(orders_count=4,sparkline_orders=[1,1,1]),4))
  self.assertFalse(valid_daily_orders(dict(orders_count=5,sparkline_orders=[1,1,1,1]),4))
  self.assertTrue(valid_daily_orders(dict(orders_count=4,sparkline_orders=[1,1,1,1]),4))
 def test_missing_marker_not_empty_success(self):
  w=types.SimpleNamespace(audit={})
  self.assertEqual(price_evidence(w)['status'],'unavailable')
 def test_completed_economics_scope_and_missing_costs(self):
  source=dict(id=1,cabinet='token_3',period_from='2026-10-31',period_to='2026-11-03',collected_at='2026-11-04T15:00:00Z',payload=[dict(data=dict(data=dict(data=[dict(nm_id=10,profit=3)])))])
  w=types.SimpleNamespace(day=date(2026,11,4),audit={},_price_completed_marker={'id':1},db=lambda *a,**kw:[source])
  e=price_evidence(w)
  self.assertEqual(e['status'],'reported_period_available')
  self.assertEqual(e['settled_cohort_profit_status'],'unavailable')
  self.assertNotIn('cost_price',e['financial_rows'][0])
  source['period_to']='2026-11-04'
  self.assertEqual(price_evidence(w)['status'],'unavailable')
 def test_incomplete_cached_day_never_zero(self):
  gaps=types.ModuleType('china_agent.wb_order_gaps');gaps.counts=lambda *a:{}
  with patch.dict(sys.modules,{'china_agent.wb_order_gaps':gaps}):
   self.assertEqual(cached_order_products(lambda k:None,date(2026,10,31),date(2026,11,3),{'1':'article'}),{})
 def test_recovery_repairs_present_rows_before_external_reads(self):
  import china_order_coverage as module
  primary=types.ModuleType('analytics.mpstats_primary');primary.products=lambda *a:([dict(nm_id=10,orders_count=8)],{'id':1})
  probe=types.ModuleType('analytics.mpstats_probe');probe.discover=lambda *a,**kw:self.fail('Unexpected API request')
  gaps=types.ModuleType('analytics.mpstats_gaps');gaps.execute_reads=lambda *a:self.fail('Unexpected API request')
  saved={};product=dict(status='complete',orders_each_day=[1,2,3,2],orders=8)
  with patch.dict(sys.modules,{'analytics.mpstats_primary':primary,'analytics.mpstats_probe':probe,'analytics.mpstats_gaps':gaps}),patch('china_price_evidence.cached_order_products',return_value={'10':product}):
   result=module.recover(lambda *a:self.fail('Unexpected database/API read'),lambda k:None,lambda k,v:saved.update({k:v}),date(2026,10,31),date(2026,11,3),[dict(nmID=10,vendorCode='article')])
  self.assertEqual(result['status'],'complete')
  self.assertEqual(result['products']['10']['orders'],8)
 def test_empty_draft_rows_still_pass_completed_economics(self):
  fake=types.ModuleType('china_codex_analysis')
  fake.Core=object;fake.active=lambda db:True;fake.digest=lambda v:'fixture';fake.text_review=None;fake.POLICY='policy'
  with patch.dict(sys.modules,{'china_codex_analysis':fake}):
   spec=importlib.util.spec_from_file_location('reports_under_test',pathlib.Path(__file__).with_name('china_codex_reports.py'))
   report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)
  class Core:
   db=None
   def ask(self,identity,kind,data,contract,validate,force):
    assert data['completed_source']['financial_rows']==[{'nm_id':10,'profit':3}]
    assert data['rows']=={}
    return validate(dict(kind='price_review',keep_rows=[],summary='Цены сохранить.')),{}
  w=types.SimpleNamespace(day=date(2026,11,4),mode='intraday',audit={},save=lambda *a:None)
  with patch('china_price_evidence.price_evidence',return_value=dict(status='reported_period_available',financial_rows=[dict(nm_id=10,profit=3)],settled_cohort_profit_status='unavailable')):
   answer,_=report.review_price(w,'Нет кандидатов.',[],force=True,core=Core())
  self.assertEqual(answer,'Цены сохранить.')
if __name__=='__main__':unittest.main()

