import sys, types, unittest
from unittest.mock import patch
from china_codex_runtime import Tools, SPECS, final_report_answer

class W:
 def get(self,key): return {}
 def catalog(self): return [('1473243817','455-NoelBag-yellow')]

class ReportContract(unittest.TestCase):
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

if __name__=='__main__':unittest.main()
