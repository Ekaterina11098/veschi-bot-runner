import ast,json,unittest
from datetime import datetime,timezone
from contextlib import nullcontext
from types import SimpleNamespace
from pathlib import Path
class Recovery(unittest.TestCase):
 def test_replaced_dispatches_are_drained_in_order(self):
  module=ast.parse(Path('scripts/conversion_watches.py').read_text())
  fn=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='drain_saved_questions')
  ns=dict(DEPLOYED_AFTER='2026-10-01',saved_network_guard=nullcontext,question_marker=lambda r:bool(r.get('tool_trace')))
  exec(compile(ast.Module(body=[fn],type_ignores=[]),'queue','exec'),ns)
  called=[]
  w=SimpleNamespace(now=datetime.now(timezone.utc),db=lambda *a,**kw:[dict(id=98,tool_trace=[1]),dict(id=99,tool_trace=[1]),dict(id=100,tool_trace=[])],question=lambda i:called.append(i) or 'sent')
  result=ns['drain_saved_questions'](w,101)
  self.assertEqual(called,[98,99,101]);self.assertEqual(len(result),3)
 def test_requested_pending_not_duplicated(self):
  module=ast.parse(Path('scripts/conversion_watches.py').read_text());fn=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='drain_saved_questions')
  ns=dict(DEPLOYED_AFTER='2026-10-01',saved_network_guard=nullcontext,question_marker=lambda r:True)
  exec(compile(ast.Module(body=[fn],type_ignores=[]),'queue','exec'),ns)
  calls=[];w=SimpleNamespace(now=datetime.now(timezone.utc),db=lambda *a,**kw:[dict(id=101)],question=lambda i:calls.append(i) or 'sent')
  ns['drain_saved_questions'](w,101);self.assertEqual(calls,[101])
 def test_source_wire_shape_is_normalized_before_readback(self):
  module=ast.parse(Path('scripts/china_new_ad_reports.py').read_text())
  source=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='source')
  node=next(n for n in source.body if isinstance(n,ast.Assign) and isinstance(n.value,ast.Call) and ast.unparse(n.value).startswith('json.loads(json.dumps(result'))
  ns=dict(json=json,result=dict(campaigns={41298169:dict(id=41298169)},amount=12.34))
  exec(compile(ast.Module(body=[node],type_ignores=[]),'normalize','exec'),ns)
  self.assertEqual(ns['result'],json.loads(json.dumps(ns['result'])))
  self.assertIn('41298169',ns['result']['campaigns'])

 def test_shared_advertising_answers_without_live_transport(self):
  from china_shared_advertising import shared
  dayrow=dict(date='2026-10-25T00:00:00Z',sum=20,sum_price=400,orders=2,clicks=80,views=1000,apps=[])
  base=dict(status='complete',period_from='2026-10-19',period_to='2026-10-24',observed_at='2026-10-25T10:00:00+00:00',batches={'0':dict(campaigns={'adverts':[dict(id=42,status=9,settings={},nm_settings=[dict(nm_id=1)])]},stats=[])})
  current=dict(observed_at='2026-10-25T17:00:00+00:00',ad_batches=[dict(data=[dict(advertId=42,days=[dayrow])])])
  w=SimpleNamespace(now=datetime(2026,10,25,17,tzinfo=timezone.utc),get=lambda k:base if k=='china_agent:advertising_source:2026-10-25:v2' else current if k=='china_agent:advertising_intraday:2026-10-25:v1' else None)
  from datetime import date
  result=shared(w,date(2026,10,25),date(2026,10,25),[])
  self.assertEqual(result['totals_by_day']['2026-10-25']['drr_pct'],5)
  self.assertEqual(result['wb_reads'],0);self.assertEqual(result['campaigns'][0]['sku_count'],1)


 def test_displayed_period_drr_is_not_post_change_drr(self):
  from china_advertising_v2 import recommend
  days=['2026-10-23','2026-10-24','2026-10-25']
  ds={d:dict(spend=s,amount=a,orders=1,views=100,clicks=10) for d,s,a in zip(days,[5,5,15],[500,500,100])}
  c=dict(id=42,status=9,settings=dict(placements=dict(search=True)),nm_settings=[dict(nm_id=1)],restrictions={})
  n=dict(nm_id=1,bids_kopecks=dict(search=28))
  r=recommend(c,n,ds,days,[dict(cid=42,nm=1,kind='price',at='2026-10-24T10:00:00+00:00')],28,200)
  self.assertAlmostEqual(r['period_drr'],25/1100*100)


 def test_truncated_membership_keeps_exact_total(self):
  from china_analytic_dialog import copy_summary
  r=copy_summary(dict(campaigns=[dict(id=42,nm_settings=[dict(nm_id=i) for i in range(31)])]))
  c=r['campaigns'][0]
  self.assertEqual(len(c['nm_settings']),12)
  self.assertEqual(c['sku_count'],31);self.assertEqual(c['nm_settings_total'],31)

if __name__=='__main__':unittest.main()
