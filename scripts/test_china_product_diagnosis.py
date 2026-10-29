import unittest,sys,types
from datetime import datetime,timezone
from contextlib import nullcontext
from unittest.mock import patch,Mock
import china_product_diagnosis as d
D=['2026-10-27','2026-10-28']
def row(cid=1,day=D[0],app=1,**v):
 return dict(campaign_id=cid,date=day,nm_id=100,app_id=app,level='SKU_app',**dict(dict(views=100,clicks=10,carts=4,orders=2,spend=5,amount=50),**v))
def ads():return dict(rows=[row(),row(day=D[1]),row(2),row(2,D[1])],coverage_complete=True)
def funnel():return {100:{D[0]:dict(opens=100,carts=20,orders=4),D[1]:dict(opens=80,carts=16,orders=3)}}
def build(a=None,f=None,events=(),history=True):return d.build([100],{100:'111-ExampleBag-black'},D,a or ads(),f or funnel(),{100:{D[0]:5,D[1]:3}},events,history)
class Tests(unittest.TestCase):
 def test_sum_across_campaigns_excludes_totals_and_fbs(self):
  a=ads();a['rows'].append(dict(row(),level='campaign_total',spend=999))
  r=build(a)['rows'][0];self.assertEqual(r['advertising_totals']['spend'],20);self.assertEqual(len(r['campaigns']),2)
  self.assertEqual(r['advertising_totals']['orders'],8);self.assertEqual(r['all_FBS_orders'][D[0]],5)
 def test_paused_historical_campaign_included(self):
  raw=[dict(advertId=1,currency='CNY',status=11,days=[dict(date=D[0],apps=[dict(appType=1,nms=[dict(nmId=100,views=5,clicks=1,atbs=1,orders=1,sum=2,sum_price=10)])])])]
  rows,seen=d.normalize_ads(raw,[100],*D);self.assertEqual(rows[0]['spend'],2);self.assertEqual(seen,{1})
 def test_duplicate_app_rejected(self):
  with self.assertRaises(ValueError):d.ad_campaigns([row(),row()],100,D)
 def test_apps_separate_then_summed(self):self.assertEqual(d.ad_campaigns([row(),row(app=32)],100,D)[1][D[0]]['spend'],10)
 def test_missing_day_or_amount_not_zero(self):
  r=d.ad_campaigns([row(amount=None)],100,D)
  self.assertIsNone(r[1][D[0]]['amount']);self.assertIsNone(r[1][D[1]]['spend']);self.assertIsNone(d.ratio(5,0))
 def test_partial_coverage_disclosed(self):
  a=ads();a['coverage_complete']=False;self.assertIn('Полнота охвата всех РК не подтверждена',d.render(build(a)))
 def test_missing_sku_not_zero(self):
  result=d.build([100],{100:'test'},D,{'rows':[]},{},{100:{D[0]:None,D[1]:None}})
  self.assertIsNone(result['rows'][0]['advertising_totals']['spend']);self.assertIn('не подтверждённый нулевой',d.render(result))
 def test_fbs_deduplicates_order_id(self):
  r=dict(id=1,nmId=100,createdAt='2026-10-27T08:00:00Z')
  self.assertEqual(d.fbs_daily({'orders':[r,r]},[100],D)[100][D[0]],1)
  with self.assertRaises(ValueError):d.fbs_daily({'orders':[r,dict(r,createdAt='2026-10-28T08:00:00Z')]},[100],D)
 def test_fbs_unknown_not_zero(self):self.assertIsNone(d.fbs_daily({},[100],D)[100][D[0]])
 def test_funnel_period_scope(self):
  s=dict(complete=True,cabinet='token_3',rows=[dict(nm_id=100,past=dict(period_from=D[0],period_to=D[0],scope='all_sources',clicks=10,cart_count=2,orders=1),selected=dict(period_from=D[1],period_to=D[1],scope='all_sources',clicks=20,cart_count=3,orders=2))])
  self.assertEqual(d.funnel_rows(s,[100],D)[100][D[1]]['opens'],20)
  s['rows'][0]['selected']['scope']='advertising'
  with self.assertRaises(ValueError):d.funnel_rows(s,[100],D)
 def test_verified_change_blocks_repeat(self):
  e=dict(event_id='e',record_type='verified_action',operational_outcome='verified',verified_at='2026-10-28T12:01:00Z',source_key='private:receipt',started_at='2026-10-28T12:00:00Z',action={'nm_ids':[100],'kind':'bid_change'})
  r=build(events=[e])['rows'][0];self.assertEqual(r['diagnosis']['signal'],'recent_change');self.assertFalse(r['history']['repeat_ready'])
  self.assertEqual(r['history']['verified_changes'][0]['first_full_day'],'2026-10-29')
 def test_unverified_history_not_execution(self):
  r=build(events=[dict(event_id='e',operational_outcome='requested',source_key='request',action={'nm_ids':[100]})])['rows'][0]
  self.assertFalse(r['history']['repeat_ready']);self.assertEqual(r['history']['verified_changes'],[]);self.assertIn('не повторять',r['diagnosis']['recommendation'])
 def test_traffic_signal_not_causality(self):
  r=build()['rows'][0];self.assertEqual(r['diagnosis']['signal'],'traffic');self.assertEqual(r['causality'],'not_established')
 def test_ad_click_signal(self):
  self.assertEqual(d.diagnose(funnel()[100][D[0]],funnel()[100][D[1]],{'views':100,'clicks':0},d.history_state([],100,D,True))['signal'],'ad_clicks')
 def test_card_cart_and_cart_order(self):
  h=d.history_state([],100,D,True);a=dict(opens=100,carts=20,orders=4)
  self.assertEqual(d.diagnose(a,dict(opens=100,carts=10,orders=3),{},h)['signal'],'card_cart')
  self.assertEqual(d.diagnose(a,dict(opens=100,carts=20,orders=1),{},h)['signal'],'cart_order')
 def test_render_limits(self):
  t=d.render(build(history=False));self.assertIn('История изменений неполна',t);self.assertIn('Малая выборка',t);self.assertIn('не складываю с FBS',t)
 def test_currency_and_commands(self):
  with self.assertRaises(ValueError):d.normalize_ads([{'advertId':1,'currency':'RUB'}],[100],*D)
  self.assertFalse(d.requested('Подними ставки во всех РК'))
 def test_all_status_catalogue_and_missing_response(self):
  a=types.ModuleType('china_analytic_dialog');a.reading=nullcontext
  b=types.ModuleType('china_change_observation');reader=Mock();reader.campaign_ids.return_value=[1,2];b.Reader=lambda *a:reader
  requests=types.ModuleType('requests');requests.get=Mock()
  catalogue=Mock(ok=True);catalogue.json.return_value={'adverts':[{'status':9,'count':1,'advert_list':[{'advertId':1}]},{'status':11,'count':1,'advert_list':[{'advertId':2}]}]}
  response=Mock(ok=True);response.json.return_value=[dict(advertId=1,currency='CNY',days=[])]
  class W:
   now=datetime(2026,10,29,15,tzinfo=timezone.utc)
   def __init__(self):self.saved={}
   def get(self,k):return self.saved.get(k)
   def save(self,k,v):self.saved[k]=v
  w=W()
  with patch.dict(sys.modules,{'china_analytic_dialog':a,'china_change_observation':b,'requests':requests}),patch.dict('os.environ',{'WB_TOKEN_3':'synthetic'}),patch('requests.get',side_effect=[catalogue,response]) as get:
   r=d.all_ads(w,[100],*D);d.all_ads(w,[100],*D)
  self.assertEqual(get.call_count,2);self.assertEqual(get.call_args.kwargs['params']['ids'],'1,2');self.assertFalse(r['coverage_complete']);self.assertEqual(r['missing_campaign_ids'],[2])
 def test_existing_evaluation_window_blocks_early_repeat(self):
  e=dict(event_id='e',record_type='verified_action',operational_outcome='verified',verified_at='2026-10-24T12:01:00Z',source_key='private:receipt',started_at='2026-10-24T12:00:00Z',comparison={'evaluate_from':'2026-10-30'},action={'nm_ids':[100],'kind':'bid_change'})
  self.assertFalse(build(events=[e])['rows'][0]['history']['repeat_ready'])
 def test_entry_uses_new_pipeline_with_bounded_selection(self):
  a=types.ModuleType('china_analytic_dialog');a.reading=nullcontext
  analyst=Mock();analyst.live.side_effect=[dict(top_yesterday_declines=[{'nm_id':100}]),dict(orders=[])]
  a.Analyst=lambda *args:analyst
  legacy=types.ModuleType('china_article_diagnostic_read');legacy.handle=Mock()
  scope=types.ModuleType('china_article_diagnostic');scope.scope=lambda *args:[]
  reports=types.ModuleType('china_wb_evidence');reports.Reports=lambda w:Mock(funnel=lambda *a:{})
  experience=types.ModuleType('china_experience');experience.decision_context=lambda *a:dict(experiences=[],total_matching_returned=0)
  class W:
   now=datetime(2026,10,29,15,tzinfo=timezone.utc)
   def catalog(self):return [('100','test')]
   def save(self,k,p):self.saved=p
  w=W()
  with patch.dict(sys.modules,{'china_analytic_dialog':a,'china_article_diagnostic_read':legacy,'china_article_diagnostic':scope,'china_wb_evidence':reports,'china_experience':experience}),patch.object(d,'all_ads',return_value={'rows':[]}):
   text,trace=d.handle(w,{'id':1,'request_text':'Разбери причину просадки продаж'},[])
  self.assertEqual(analyst.live.call_count,2);self.assertEqual(trace[0]['name'],'product_wide_diagnosis');self.assertEqual(w.saved['rows'][0]['nm_id'],100)
  legacy.handle.assert_not_called()
if __name__=='__main__':unittest.main()
