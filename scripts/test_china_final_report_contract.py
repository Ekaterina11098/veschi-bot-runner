import sys, types, unittest, asyncio, json, hashlib
from unittest.mock import patch
from china_codex_runtime import Tools, SPECS, final_report_answer

class W:
 def get(self,key): return {}
 def catalog(self): return [('1473243817','455-NoelBag-yellow')]

class ReportContract(unittest.TestCase):
 def test_native_recovery_bound_to_original_product_and_dates(self):
  from china_menu_analytics import native_funnel_request,PREFIX
  text='/codex show general funnel for 021 nmid 1473244991 for 2026-11-05 to 2026-11-11 full msk days. read only.'
  scope={'nm_id':1473244991,'date_from':'2026-11-05','date_to':'2026-11-11'}
  self.assertEqual(native_funnel_request(text,scope),PREFIX+'1473244991 2026-11-05 2026-11-11')
  for wrong in [dict(scope,nm_id=1473244990),dict(scope,date_from='2026-11-01'),dict(scope,execute=True)]:
   with self.assertRaises(ValueError):native_funnel_request(text,wrong)
 def test_restored_thread_gets_current_tools_without_rewriting_history(self):
  from china_codex_appserver import restore_rollout,encode
  history=b'{"type":"response_item","payload":{"text":"retained work history"}}\n'
  raw=json.dumps({'type':'session_meta','payload':{'id':'test-thread','dynamic_tools':[{'name':'old'}]}}).encode()+b'\n'+history
  state={'thread_id':'test-thread','rollout_gzip_b64':encode(raw),'rollout_sha256':hashlib.sha256(raw).hexdigest()}
  restored=restore_rollout(state,SPECS)
  self.assertEqual(restored.split(b'\n',1)[1],history)
  self.assertEqual(json.loads(restored.splitlines()[0])['payload']['dynamic_tools'],SPECS)
  state['rollout_sha256']='incorrect'
  with self.assertRaises(ValueError):restore_rollout(state,SPECS)
 def tools(self):
  with patch.dict(sys.modules,{'china_analytic_dialog':types.SimpleNamespace(Analyst=lambda *a:None)}):
   return Tools(W(),{'id':303})
 def test_funnel_uses_same_scoped_collector_and_keeps_table(self):
  calls=[]
  def funnel(w,job,text):
   calls.append((job['id'],text));return 'Общая воронка\n|Дата|Заказы|\n|---|---|\n|2026-11-10|8|'
  with patch.dict(sys.modules,{'china_menu_analytics':types.SimpleNamespace(funnel=funnel,PREFIX='Общая воронка · запрос меню: ')}):
   t=self.tools();out=t('collect_general_funnel',{'nm_id':1473243817,'date_from':'2026-11-10','date_to':'2026-11-10'})
  self.assertEqual(calls,[(303,'Общая воронка · запрос меню: 1473243817 2026-11-10 2026-11-10')])
  self.assertTrue(out['canonical_report'])
  self.assertEqual(final_report_answer(t,'Сбор сделаю потом'),out['answer'])
 def test_failed_collection_cannot_create_ready_report(self):
  def fail(*a):raise ValueError('Нет сохранённой истории')
  with patch.dict(sys.modules,{'china_menu_analytics':types.SimpleNamespace(funnel=fail,PREFIX='scope:')}):
   t=self.tools()
   with self.assertRaises(ValueError):t('collect_general_funnel',{'nm_id':1473243817,'date_from':'2026-11-10','date_to':'2026-11-10'})
  self.assertEqual(t.final_reports,{})
 def test_plain_dialogue_not_replaced(self):
  self.assertEqual(final_report_answer(self.tools(),'Пояснение без отчёта'),'Пояснение без отчёта')
 def test_funnel_tool_is_explicitly_scoped(self):
  s=next(x for x in SPECS if x['name']=='collect_general_funnel')
  self.assertEqual(set(s['inputSchema']['required']),{'nm_id','date_from','date_to'})
  self.assertFalse(s['inputSchema']['additionalProperties'])
 def test_dependency_failure_is_recorded_before_any_model_start(self):
  from china_codex_runtime import execute, CHAT, ROOT
  from contextlib import nullcontext
  class BrokenWorker:
   def __init__(self):self.state={}
   def get(self,key):return self.state.get(key)
   def save(self,key,value,**kw):self.state[key]=value;return True
   def catalog(self):raise ModuleNotFoundError('business_agents')
  w=BrokenWorker();job={'id':305,'chat_id':CHAT,'sender_id':5122667182}
  modules={'china_analytic_dialog':types.SimpleNamespace(Analyst=lambda *a:None,reading=nullcontext)}
  with patch.dict(sys.modules,modules),patch('china_codex_runtime.Client') as client:
   with self.assertRaises(ModuleNotFoundError):execute(w,job,{'job_id':305}).send(None)
   client.assert_not_called()
  self.assertEqual(w.state[ROOT+'job:305']['status'],'blocked_before_model')
  self.assertFalse(w.state[ROOT+'job:305']['model_request_started'])
  self.assertEqual(w.state[ROOT+'job:305']['model_calls'],0)

if __name__=='__main__':unittest.main()
