import copy,unittest
from china_conversion_explanation import explain
from test_conversion_watches import Memory,job

VALUE={'source':'MPStats','cabinet':'Китай','article':'52-NoelBag-fuchsia','date_from':'2026-10-12','date_to':'2026-10-16','complete':True,
 'daily':[{'date':'2026-10-'+str(day),'views':views,'orders':orders,'nm_id':'1473243825','article':'52-NoelBag-fuchsia','cabinet':'token_3'} for day,views,orders in [(12,37,4),(13,54,3),(14,119,3),(15,177,3),(16,202,1)]]}
PARENT={'id':44,'answer':'report','tool_trace':[{'name':'saved_conversion_history','arguments':{'article':'52-NoelBag-fuchsia','nm_id':'1473243825'},'result':VALUE}]}
MARKER={'name':'china_saved_question','parent_job_id':44,'reply_message_id':5,'message_id':6}

class Explanation(unittest.TestCase):
 def test_exact_reply_and_quantitative_depth(self):
  text,trace=explain('А почему снизилась конверсия?',MARKER,[PARENT])
  for expected in ('52-NoelBag-fuchsia','2026-10-12–2026-10-16','177 → 202','3 → 1','1,69% → 0,50%','-1,20 п.п.','37 → 202','4 → 1','10,81% → 0,50%','-10,32 п.п.','не установлено'):
   self.assertIn(expected,text)
  self.assertNotIn('снижение интереса',text.casefold());self.assertEqual(trace[0]['arguments']['parent_job_id'],44)
 def test_no_unverified_quote_context(self):
  result=explain('А почему снизилась конверсия?',dict(MARKER,parent_job_id=99),[PARENT])
  self.assertNotIn('177',result[0]);self.assertEqual(result[1],[])
 def test_does_not_cross_product_scope(self):
  parent=copy.deepcopy(PARENT);parent['tool_trace'][0]['result']['daily'][2]['nm_id']='52'
  text,trace=explain('А почему снизилась конверсия?',MARKER,[parent]);self.assertIn('не подтверждены',text);self.assertEqual(trace,[])
 def test_missing_days_not_zero(self):
  parent=copy.deepcopy(PARENT);parent['tool_trace'][0]['result']['complete']=False
  text,trace=explain('А почему снизилась конверсия?',MARKER,[parent]);self.assertIn('пропуски не считаются нулями',text);self.assertNotIn('0,50%',text)
 def test_zero_views_not_divided(self):
  parent=copy.deepcopy(PARENT);parent['tool_trace'][0]['result']['daily'][-1]['views']=0
  text,_=explain('А почему?',MARKER,[parent]);self.assertIn('сравнить нельзя',text)
 def test_increase_not_called_decrease(self):
  parent=copy.deepcopy(PARENT);parent['tool_trace'][0]['result']['daily'][-1]['orders']=10
  text,_=explain('А почему снизилась конверсия?',MARKER,[parent]);self.assertIn('снижение здесь не подтверждается',text)
 def test_worker_bypasses_model_and_collectors_for_parent_evidence(self):
  w=Memory();w.model_request=lambda *a:(_ for _ in ()).throw(AssertionError('model'))
  w.collect=lambda *a:(_ for _ in ()).throw(AssertionError('collect'))
  j=job('А почему снизилась конверсия?');j['tool_trace']=[MARKER]
  text,trace=w.saved_question(j,[PARENT]);self.assertIn('1,69% → 0,50%',text);self.assertEqual(trace[0]['name'],'saved_conversion_explanation')
 def test_unrelated_question_keeps_other_route(self):self.assertIsNone(explain('Покажи остатки',MARKER,[PARENT]))

if __name__=='__main__':unittest.main()
