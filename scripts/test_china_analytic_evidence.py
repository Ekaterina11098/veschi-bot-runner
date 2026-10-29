import unittest
from datetime import datetime,timezone
from unittest.mock import Mock
import china_analytic_evidence as g
class W:
 now=datetime(2026,10,29,15,tzinfo=timezone.utc)
 def catalog(self):return [('100','111-ExampleBag-black'),('200','222-ExampleBag-white')]
def p(q,h=[]):return g.plan(W(),{'request_text':q},h)
def trace(r):return [{'name':'get_live_data','result':dict(source='synthetic',observed_at='2026-10-29T15:00:00Z',**r)}]
class Tests(unittest.TestCase):
 def test_route_and_completed_week(self):
  x=p('Сколько заказов за неделю?')
  self.assertEqual(x['topic'],'orders');self.assertEqual(x['period_from'],'2026-10-22');self.assertEqual(x['period_to'],'2026-10-28')
 def test_context_keeps_exact_article(self):
  x=p('А за неделю?',[{'request_text':'Сколько показов у 111-ExampleBag-black?'}])
  self.assertEqual(x['topic'],'advertising');self.assertEqual(x['arguments']['nm_ids'],[100])
 def test_no_context_or_personal_collection(self):
  for q in ['Как приготовить суп?','Что такое ДРР?','Запомни: кратко','Давай поднимем ставки','А за неделю?']:
   self.assertIsNone(p(q),q)
 def test_today_explicit_and_campaign_scope(self):
  x=p('Посмотри заказы и расход РК 41234567 сегодня')
  self.assertEqual(x['tool'],'get_saved_campaign');self.assertEqual(x['arguments']['campaign_id'],41234567);self.assertTrue(x['intraday'])
 def test_unknown_article_not_whole_cabinet(self):
  x=p('Сколько заказов у 333-UnknownBag-black?');an=Mock()
  r=g.preflight(an,x);self.assertFalse(r['result']['available']);an.live.assert_not_called()
 def test_preflight_exact_source_args(self):
  x=p('Сколько заказов сегодня?');an=Mock();an.live.return_value={'source':'synthetic','total_orders':5}
  r=g.preflight(an,x)
  an.live.assert_called_once_with('orders',[],'2026-10-29','2026-10-29');self.assertEqual(r['result']['total_orders'],5)
 def test_transport_failure_is_not_zero(self):
  an=Mock();an.live.side_effect=RuntimeError('unavailable')
  r=g.preflight(an,p('Сколько заказов сегодня?'));self.assertFalse(r['result']['available']);self.assertNotIn('total_orders',r['result'])
 def test_wrong_cabinet_and_incomplete_day_claim(self):
  self.assertTrue(g.review('5 заказов',trace({'cabinet':'token_2','total_orders':5}),p('Сколько заказов сегодня?')))
  self.assertTrue(g.review('Заказы упали: 5',trace({'total_orders':5}),p('Сколько заказов сегодня?')))
  self.assertFalse(g.review('Предварительный ориентир: заказы упали, 5',trace({'total_orders':5}),p('Сколько заказов сегодня?')))
 def test_memory_and_calculator_are_not_source(self):
  t=[{'name':'read_shared_memory','result':{'source':'old','orders':99}},{'name':'calculate','result':{'value':99}}]
  self.assertTrue(g.review('99 заказов',t,p('Сколько заказов сегодня?')))
 def test_grounded_number_and_decimal_not_date(self):
  t=trace({'total_orders':5,'ratio':0.55})
  self.assertFalse(g.review('На 29.10.2026 18:00: 5 заказов, 0,55%.',t,p('Сколько заказов сегодня?')))
  self.assertTrue(g.review('Конверсия 0,99%',t,p('Сколько заказов сегодня?')))
 def test_article_code_is_identity_not_a_metric(self):
  self.assertFalse(g.review('111-ExampleBag-black: 5 заказов',trace({'total_orders':5}),p('Сколько заказов сегодня?')))
 def test_unsupported_and_user_claim_rejected(self):
  t=trace({'total_orders':5})
  self.assertTrue(g.review('99 заказов',t,p('Сколько заказов сегодня?'),'У нас 99 заказов?'))
 def test_calculation_requires_grounded_operands(self):
  t=trace({'orders':5,'clicks':1000})
  t.append({'name':'calculate','arguments':{'expression':'5/1000*100'},'result':{'value':0.5}})
  self.assertFalse(g.review('0,5%',t,p('Сколько заказов сегодня?')))
  t[-1]['arguments']['expression']='99/1000*100';t[-1]['result']['value']=9.9
  self.assertTrue(g.review('9,9%',t,p('Сколько заказов сегодня?')))
 def test_unknown_and_partial_source_rejected(self):
  for extra in [{'available':False},{'complete':False}]:
   self.assertTrue(g.review('5 заказов',trace(dict(total_orders=5,**extra)),p('Сколько заказов сегодня?')))
 def test_zero_drr_requires_positive_denominator(self):
  for amount in [0,None]:
   self.assertTrue(g.review('ДРР 0%',trace({'sum':0,'sum_price':amount}),p('Какая ДРР сегодня?')))
  self.assertFalse(g.review('ДРР 0%',trace({'sum':0,'sum_price':100}),p('Какая ДРР сегодня?')))
 def test_tool_availability_not_invented(self):
  self.assertTrue(g.review('Инструмента нет',trace({'total_orders':5}),p('Сколько заказов сегодня?')))

class DialogIntegration(unittest.TestCase):
 def modules(self):
  import types
  out={}
  def mod(name,**fields):
   m=types.ModuleType(name);m.__dict__.update(fields);out[name]=m
  mod('china_conversion_context',handle=lambda *a:None)
  mod('china_zero_order_price_command',handle=lambda *a:None,status_answer=lambda *a:None)
  mod('china_zero_orders',answer=lambda *a:None)
  mod('china_article_diagnostic_read',handle=lambda *a:None)
  mod('business_agents',conversation=types.SimpleNamespace(tools=lambda _:[]))
  mod('business_agents.data',Data=lambda *a:object())
  mod('china_shared_memory',context=lambda *a,**k:{},is_work=lambda _:False)
  mod('china_budget_context',dialog_context=lambda *a:{},RULES='')
  mod('china_loss_control',marker=lambda _:{})
  mod('china_experience',decision_context=lambda _:dict(experiences=[],recent_changed_nm_ids=[]),search=lambda *a:{})
  mod('china_reply_quality',RULES='',current_memberships=lambda _:[])
  mod('china_article_diagnostic',RULES='')
  mod('china_saved_products',ground_answer=lambda text,trace:text)
  mod('china_model_usage',metered_request=lambda request,body,**kwargs:request(body),task_type=lambda _: 'synthetic')
  return out
 def run_dialog(self,q,answers):
  import copy,sys
  from unittest.mock import patch
  import china_analytic_dialog as a
  class Worker(W):
   def __init__(self):
    self.mem={a.POLICY:dict(enabled=True,model='synthetic'),a.MEMORY:dict(revision=1)}
    self.bodies=[]
   def get(self,k):return copy.deepcopy(self.mem.get(k))
   def save(self,k,v):self.mem[k]=copy.deepcopy(v)
   def model_request(self,body):
    self.bodies.append(copy.deepcopy(body));text=answers[min(len(self.bodies)-1,len(answers)-1)]
    return dict(output=[dict(type='message',content=[dict(type='output_text',text=text)])])
  w=Worker()
  with patch.dict(sys.modules,self.modules()),patch.object(a.Analyst,'live',return_value={'source':'synthetic','observed_at':'2026-10-29T15:00:00Z','total_orders':5}) as live:
   result=a.answer(w,dict(id=1,chat_id=-1,request_text=q),[])
  return result,w,live
 def test_real_answer_reads_before_first_model_and_repairs_claim(self):
  (text,trace),w,live=self.run_dialog('Сколько заказов сегодня?',['Сегодня 99 заказов.','Сегодня 5 заказов.'])
  live.assert_called_once();self.assertEqual(len(w.bodies),2);self.assertIn('5 заказов',text)
  self.assertTrue(any(t['name']=='get_live_data' for t in w.bodies[0]['tools']))
  self.assertTrue(any(t['name']=='analytic_evidence_preflight' for t in trace))
  self.assertIn('source_result',str(w.bodies[0]['input']))
 def test_real_answer_blocks_persistent_hallucination(self):
  (text,trace),w,live=self.run_dialog('Сколько заказов сегодня?',['Сегодня 99 заказов.'])
  self.assertNotIn('99',text);self.assertIn('не прошёл проверку',text);self.assertLessEqual(len(w.bodies),10)
 def test_personal_reply_does_not_collect_business_data(self):
  (text,_),w,live=self.run_dialog('Как приготовить суп?',['Сварите овощи.'])
  live.assert_not_called();self.assertEqual(text,'Сварите овощи.')

if __name__=='__main__':unittest.main()
