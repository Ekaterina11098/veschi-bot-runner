import sys,types,unittest,tempfile,copy
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from PIL import ImageDraw
from advertising_budget_evidence import load_daily_table_view
from advertising_daily_png import render_daily_png
class SavedStore:
 def __init__(self):
  self.catalog=[dict(report='stats',period_from='2026-10-13',period_to='2026-10-19',start_row=0,total=2,observed_at='2026-10-20T05:00:00Z',rows=[dict(id=10,wb_id=1,ac_spending_sum=140,status_id=9),dict(id=20,wb_id=2,ac_spending_sum=36,status_id=11)])]
  self.day=dict(report='products',campaign_id=10,scope_nm_id=None,spending_reconciled=True,period_from='2026-10-19',period_to='2026-10-19',sku_order_basis='direct_only',totals=dict(ac_spending_sum=10,ac_orders_sum=100,ac_orders=1,ac_orders_associated=0),rows=[dict(nm_id=111,ac_spending_sum=10,ac_orders_sum=100,ac_orders=1)])
  self.fallback=dict(report='days',campaign_id=20,scope_nm_id=None,spending_reconciled=True,period_from='2026-10-19',period_to='2026-10-19',totals=dict(ac_spending_sum=0,ac_orders_sum=0,ac_orders=0,ac_orders_associated=0),rows=[dict(date='2026-10-19',ac_spending_sum=0,ac_orders_sum=0,ac_orders=0)])
 def registration(self):return dict(chat_id=55)
 def cache_get(self,k):return dict(cabinet='token_2',chat_id=55,campaign_ids=[1,2]) if k=='advertising:ip:daily-overview-scope:v1' else None
 def db(self,method,table,params=None):
  assert method=='GET'
  src=params['source'][3:]
  if src=='advertising_active_configuration':return [dict(payload=dict(campaign_ids=[1]))]
  if src=='mpstats_campaign_catalog':return [dict(payload=self.catalog)]
  if src=='advertising_campaign_budgets':return []
  if src=='mpstats_campaign_report':
   return [dict(id=2,payload=[self.fallback])] if params.get('payload->0->>report')=='eq.days' else [dict(id=1,payload=[self.day])]
  raise AssertionError(src)
class WeeklySaved(unittest.TestCase):
 def load(self,s):
  payload=types.ModuleType('analytics.payload_storage');payload.decode_rows=lambda x:x
  data=types.ModuleType('business_agents.data')
  class Data:
   def __init__(self,*a):pass
   def snapshot(self,*a):return dict(rows=[dict(nmID=111,vendorCode='Article')])
  data.Data=Data
  modules={'analytics':types.ModuleType('analytics'),'analytics.payload_storage':payload,'business_agents':types.ModuleType('business_agents'),'business_agents.data':data}
  with patch.dict(sys.modules,modules):return load_daily_table_view(s,datetime(2026,10,20,6,tzinfo=timezone.utc))
 def test_saved_week_and_paused_scope(self):
  v=self.load(SavedStore());self.assertEqual([c['campaign_id'] for c in v['campaigns']],[1,2])
  self.assertEqual([c['weekly_spend'] for c in v['campaigns']],[140,36])
  self.assertEqual(v['weekly_period_from'],'2026-10-13');self.assertEqual(v['weekly_period_to'],'2026-10-19')
 def test_explicit_day_zero_not_empty_response(self):
  v=self.load(SavedStore());c=v['campaigns'][1];self.assertTrue(c['metrics_complete']);self.assertEqual(c['spend'],0)
  self.assertEqual(c['sku_order_basis'],'direct_only')
 def test_empty_fallback_unknown(self):
  s=SavedStore();s.fallback['rows']=[]
  c=self.load(s)['campaigns'][1];self.assertFalse(c['metrics_complete']);self.assertIsNone(c['spend'])
 def test_aggregate_nonzero_not_invented_sku(self):
  s=SavedStore();s.fallback['totals'].update(ac_spending_sum=10,ac_orders=1,ac_orders_sum=100);s.fallback['rows'][0].update(ac_spending_sum=10,ac_orders=1,ac_orders_sum=100)
  c=self.load(s)['campaigns'][1];self.assertTrue(c['metrics_complete']);self.assertEqual(c['sku_order_basis'],'aggregate_only');self.assertEqual(c['above5'],[])
 def test_wrong_week_is_not_reused(self):
  s=SavedStore();s.catalog[0]['period_from']='2026-10-12'
  self.assertTrue(all(c['weekly_spend'] is None for c in self.load(s)['campaigns']))
 def test_missing_catalog_page_not_zero(self):
  s=SavedStore();s.catalog[0]['total']=3
  self.assertTrue(all(c['weekly_spend'] is None for c in self.load(s)['campaigns']))
 def test_png_weekly_and_no_delivery_classification(self):
  view=self.load(SavedStore());seen=[];native=ImageDraw.ImageDraw.text
  def record(obj,xy,text,*a,**kw):seen.append(str(text));return native(obj,xy,text,*a,**kw)
  with tempfile.TemporaryDirectory() as d:
   with patch.object(ImageDraw.ImageDraw,'text',record):images=render_daily_png(view,d)
  self.assertEqual([x['kind'] for x in images],['drr','budgets'])
  self.assertIn('7 дн.: 36 ₽',seen);self.assertIn('За день не откручивалась',seen)
  self.assertTrue(any('176 ₽' in x for x in seen))
if __name__=='__main__':unittest.main()
