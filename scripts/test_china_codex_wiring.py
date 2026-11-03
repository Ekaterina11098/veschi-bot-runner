import copy,sys,types,unittest
from unittest.mock import patch
from china_codex_reports import review_advertising,review_price
from china_codex_analysis import POLICY
from china_codex_routing import cloud_only,bound_execution
class Store:
 def __init__(self,p=None):self.p=p or {}
 def get(self,k):return self.p if k==POLICY else None
class Core:
 def __init__(self,result,p=None):self.result=result;self.db=Store(p);self.data=None
 def ask(self,identity,kind,data,contract,validate,force=False):
  self.data=data;return validate(copy.deepcopy(self.result)),{'key':'private','source_channel':'codex_cloud'}
def fixture():
 a=dict(id='1:2',kind='ad_set_bid',campaign_id=1,nm_id=2,old_minor=31,target_minor=28,placement='search')
 metric=dict(spend=40,amount=100,orders=1,clicks=140,views=1000)
 row=dict(nm=2,article='2-Bag-black',period=metric,decision='Снизить',action=a)
 bundle=dict(day='2026-11-03',days=['2026-11-02'],campaigns=[dict(id=1,status=9,payment='cpc',focus=[row],attention=[copy.deepcopy(row)],period=metric)])
 source=dict(period_from='2026-11-02',period_to='2026-11-02',batches={},catalogue=dict(rows=[dict(nmID=2,vendorCode='2-Bag-black')]))
 result=dict(kind='advertising_review',decisions=[],directions={k:dict(status='checked',note='Проверено')for k in ['raise','add','reduce','exclude']},research=[])
 return a,bundle,source,result
class Wiring(unittest.TestCase):
 def test_cloud_rejection_removes_action_without_rewriting_observed_metrics(self):
  a,b,s,v=fixture();out=review_advertising(None,b,s,'test',force=True,core=Core(v))
  self.assertEqual([],out['campaigns'][0]['attention']);self.assertIsNone(out['campaigns'][0]['focus'][0]['action'])
  self.assertEqual(b['campaigns'][0]['period'],out['campaigns'][0]['period'])
  self.assertEqual(a,b['campaigns'][0]['focus'][0]['action'])
 def test_owner_withdrawn_action_never_enters_allowed_model_choices(self):
  a,b,s,v=fixture();v['decisions']=[dict(id='1:2',note='Снизить')]
  core=Core(v,dict(owner_withdrawn_actions=[dict(campaign_id=1,nm_id=2,kind='ad_set_bid')]))
  with self.assertRaises(ValueError):review_advertising(None,b,s,'test',force=True,core=core)
  self.assertEqual({},core.data['allowed_actions'])
 def test_private_detailed_research_is_not_dumped_in_public_recommendation(self):
  a,b,s,v=fixture();v['research']=[dict(nm_id=2,campaign_id=1,direction='raise',note='Длинное частное обоснование. '*20)]
  out=review_advertising(None,b,s,'test',force=True,core=Core(v))
  public=out['campaigns'][0]['codex_research_recommendations'][0]
  self.assertLess(len(public),160);self.assertNotIn('Длинное',public);self.assertFalse(out['campaigns'][0]['attention'])
 def test_price_selection_cannot_change_exact_source_prices(self):
  class Worker:
   day='2026-11-03';mode='morning';audit={}
   def get(self,k):return None
  text='Артикул | Цена\n--- | ---\n1-Bag-black | 100 → 105\n2-Bag-white | 200 → 210'
  out,trace=review_price(Worker(),text,[],True,Core(dict(kind='price_review',keep_rows=['row:2'],summary='Сохранить только проверенное предложение.')))
  self.assertIn('100 → 105',out);self.assertNotIn('200 → 210',out);self.assertEqual('codex_cloud',trace[0]['source_channel'])
 def test_old_analysis_is_disabled_only_at_active_verified_cutover(self):
  self.assertFalse(cloud_only(Store(dict(status='shadow',legacy_analysis_enabled=False))))
  self.assertTrue(cloud_only(Store(dict(status='active',legacy_analysis_enabled=False))))
 def test_phrase_make_table_does_not_become_execution_even_when_reply_is_bound(self):
  loss=types.ModuleType('china_loss_control');loss.is_all=lambda text:text=='Сделай всё';loss.marker=lambda job:job['marker']
  ads=types.ModuleType('china_advertising_plans');ads.bid_confirmation=lambda text:False
  selected=types.ModuleType('china_daily_selected');selected.selected_command=lambda text:None
  class IO:
   def get(self,key):return {'chat_id':-1004342917488}
  job=dict(request_text='Сделай таблицу',marker=dict(bot_id=8780468043,reply_message_id=665))
  with patch.dict(sys.modules,{'china_loss_control':loss,'china_advertising_plans':ads,'china_daily_selected':selected}):
   self.assertFalse(bound_execution(IO(),job))
   self.assertTrue(bound_execution(IO(),dict(job,request_text='Сделай всё')))
if __name__=='__main__':unittest.main()
