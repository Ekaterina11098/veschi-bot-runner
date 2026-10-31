import copy,json,sys,types,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch,Mock
import china_analytic_evidence as g
class W:
 now=datetime(2026,10,31,18,54,tzinfo=timezone.utc)
 def __init__(self):self.mem={}
 def catalog(self):return [('1473245494','143-ReginaBag-black'),('1473244984','023-AlessiaBag-black'),('1473243895','045-NoelBag-ginger')]
 def get(self,key):return copy.deepcopy(self.mem.get(key))
 def save(self,key,value):self.mem[key]=copy.deepcopy(value)
class PavelReplay(unittest.TestCase):
 def test_real_questions_route_scope_and_period(self):
  from china_ad_expense_table import requested
  for case in json.loads(Path(__file__).with_name('china_pavel_questions31.json').read_text(encoding='utf-8')):
   with self.subTest(case=case['id']):
    if case.get('expense'):
     self.assertTrue(requested(case['question'],case.get('history',[])));continue
    p=g.plan(W(),dict(request_text=case['question']),case.get('history',[]))
    if case.get('no_plan'):self.assertIsNone(p);continue
    self.assertEqual(p['topic'],case['topic']);self.assertEqual(p['arguments']['nm_ids'],case['ids'])
    self.assertEqual(p['period_from'],case['first']);self.assertEqual(p['period_to'],case['last'])
    self.assertEqual([a['topic'] for a in p.get('additional_reads',[])],case.get('additional',[]))
 def test_ambiguous_model_does_not_read_whole_cabinet(self):
  w=W();w.catalog=lambda:[('1','143-Bag-black'),('2','143-Bag-white')]
  p=g.plan(w,dict(request_text='Сколько сегодня заказов на модели143?'),[])
  a=Mock();r=g.preflight(a,p);self.assertFalse(r['result']['available']);a.live.assert_not_called()
 def test_multi_input_partial_preserves_good_source(self):
  p=g.plan(W(),dict(request_text='Заказы и выкупы 023-AlessiaBag-black за неделю'),[])
  a=Mock();a.live.side_effect=[dict(source='own cohort',rows=[dict(is_payed=2,finished_orders=4)]),RuntimeError('unavailable')]
  r=g.preflight(a,p);self.assertFalse(r['result']['coverage_complete']);self.assertEqual(len(g.evidence([r])),1)
  self.assertEqual(a.live.call_count,2)
 def test_economics_reads_exact_inputs_without_permissions(self):
  w=W();p=g.plan(w,dict(request_text='045-NoelBag-ginger в плюс продаём?'),[])
  a=Mock();a.w=w;a.live.return_value=dict(source='synthetic',rows=[])
  r=g.preflight(a,p)
  self.assertEqual([c.args[0] for c in a.live.call_args_list],['products','prices','stock'])
  self.assertTrue(all(c.args[1]==[1473243895] for c in a.live.call_args_list))
  self.assertFalse(r['result'].get('grants_action_permission',False))
 def test_expense_scope_never_leaks_other_skus(self):
  import china_ad_expense_table as e
  w=W();source=dict(observed_at=w.now.isoformat(),date_msk='2026-10-31',stats=[dict(advertId=1,days=[dict(apps=[dict(nms=[dict(nmId=1473243895,sum=5,sum_price=0,orders=0),dict(nmId=1473245494,sum=99,sum_price=1,orders=1)])])])])
  with patch.object(e,'read',return_value=source):
   text,trace=e.handle(w,dict(chat_id=-1004342917488,request_text='Таблица расходов и ДРР 045-NoelBag-ginger'),[])
  self.assertIn('045-NoelBag-ginger',text);self.assertNotIn('143-ReginaBag-black',text)
 def test_fresh_scoped_transport_uses_exact_ids_despite_old_context(self):
  import china_analytic_dialog as a
  w=W();an=a.Analyst(w,dict(id=-1,request_text='проверка'),[]);an.cached_product_context_supplied=True
  module=types.ModuleType('china_product_current');module.scoped=Mock(return_value=dict(source='fresh exact',rows=[]))
  with patch.dict(sys.modules,{'china_product_current':module}):
   an.live('prices',[1473243895],'2026-10-01','2026-10-30')
  self.assertEqual(module.scoped.call_args.args[2],[1473243895])
 def test_saved_buyouts_keep_sales_distinct(self):
  from china_saved_products import saved_products
  row=dict(nm_id=1473243895,sa_name='045-NoelBag-ginger',is_payed=1,finished_orders=5,sales_count=2,orders_count=5)
  obs=dict(tool='lk_wb_products',status='received',scope_verified=True,arguments=dict(date_from='2026-10-01',date_to='2026-10-30'),data=dict(data=dict(data=[row],total=1,need_update=0)))
  w=W();w.db=lambda *a,**kw:[dict(id=1,collected_at=w.now.isoformat(),payload=[obs])]
  r=saved_products(w,'2026-10-01','2026-10-30',[1473243895])['rows'][0]
  self.assertEqual(r['sales_count'],2);self.assertEqual(r['is_payed'],1);self.assertEqual(r['buyout_pct'],20)
 def test_missing_orders_array_is_not_zero(self):
  import china_analytic_dialog as a,os
  from datetime import date
  module=types.ModuleType('requests')
  module.get=lambda *args,**kwargs:types.SimpleNamespace(ok=True,json=lambda:{})
  with patch.dict(sys.modules,{'requests':module}),patch.dict(os.environ,{'WB_TOKEN_3':'synthetic'}):
   with self.assertRaisesRegex(ValueError,'не ноль'):
    a.Analyst(W(),{},[]).collect('orders',[1473243895],date(2026,10,30),date(2026,10,30))
 def test_exact_scope_read_budget_is_bounded(self):
  import china_analytic_dialog as a
  an=a.Analyst(W(),{},[]);an.fresh_reads=6
  module=types.ModuleType('china_product_current');module.scoped=Mock()
  with patch.dict(sys.modules,{'china_product_current':module}):
   with self.assertRaises(ValueError):an.live('stock',[1473243895],'2026-10-01','2026-10-30')
  module.scoped.assert_not_called()
if __name__=='__main__':unittest.main()
