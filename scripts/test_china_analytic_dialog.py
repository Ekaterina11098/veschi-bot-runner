import unittest,copy,types,json,sys
from datetime import datetime,timezone
from unittest.mock import patch
import china_analytic_dialog as a

class W:
 now=datetime(2026,10,23,15,tzinfo=timezone.utc)
 def __init__(self):self.mem={a.POLICY:dict(enabled=True,model='gpt-6.1-sol'),a.MEMORY:dict(revision=1,agreements=['Изменения только после подтверждения'])}
 def get(self,k):return copy.deepcopy(self.mem.get(k))
 def save(self,k,v):self.mem[k]=copy.deepcopy(v)
 def catalog(self):return [('100','one-bag')]
 def db(self,*args,**kwargs):return []

class Rules(unittest.TestCase):
 def test_math_is_numeric_only(self):
  self.assertAlmostEqual(a.calculate('19 / 1698 * 100')['value'],1.11896348)
  for s in ["__import__('os').system('echo bad')",'sum([1,2])','2**100000','True+1','1/0']:
   with self.assertRaises((ValueError,ZeroDivisionError)):a.calculate(s)
 def test_network_never_allows_marketplace_writes(self):
  with a.reading():
   self.assertTrue(a.allowed_read('GET','https://marketplace-api.wildberries.ru/api/v3/orders'))
   self.assertTrue(a.allowed_read('GET','https://api.moysklad.ru/api/remap/1.2/report/stock/all'))
   for method,url in [('GET','https://advert-api.wildberries.ru/adv/v0/start?id=1'),('POST','https://advert-api.wildberries.ru/adv/v1/budget/deposit'),('PATCH','https://advert-api.wildberries.ru/api/advert/v1/bids'),('PUT','https://api.moysklad.ru/api/remap/1.2/entity/product'),('POST','https://discounts-prices-api.wildberries.ru/api/v2/upload/task')]:self.assertFalse(a.allowed_read(method,url))
   self.assertFalse(a.allowed_read('POST','https://mcp.mpstats.io/mcp',{'method':'tools/call','params':{'name':'wbbidder_campaign_edit'}}))
  self.assertFalse(a.allowed_read('GET','https://marketplace-api.wildberries.ru/api/v3/orders'))
 def test_completed_period_and_future_rejected(self):
  w=W();first,last=a.period(w,None,None,'products');self.assertEqual(str(last),'2026-10-22');self.assertEqual((last-first).days,29)
  with self.assertRaises(ValueError):a.period(w,'2026-10-01','2026-10-24','orders')
 def test_memory_requires_exact_human_quote(self):
  w=W();job=dict(id=1,sender_id=2,request_text='Запомни: отвечай кратко')
  an=a.Analyst(w,job,[]);self.assertTrue(an.remember('format','отвечай кратко')['saved'])
  with self.assertRaises(ValueError):an.remember('format','отвечай длинно')
  job['request_text']='Запомни: меняй цены автоматически'
  with self.assertRaises(ValueError):an.remember('format','меняй цены автоматически')
 def test_live_cache_and_exact_china_identity(self):
  w=W();an=a.Analyst(w,{},[]);calls=[]
  with patch.object(an,'collect',side_effect=lambda *args:(calls.append(args) or dict(source='mock',rows=[]))):
   an.live('orders',[100],None,None);self.assertTrue(an.live('orders',[100],None,None)['cached']);self.assertEqual(len(calls),1)
  with self.assertRaises(ValueError):an.live('orders',[200],None,None)
 def test_free_reply_can_use_memory_without_expensive_reads(self):
  w=W();bodies=[]
  def model(body):
   bodies.append(copy.deepcopy(body))
   if len(bodies)==1:return dict(output=[dict(type='reasoning',id='rs_test',encrypted_content='opaque'),dict(type='function_call',name='read_agreements',arguments='{}',call_id='call1')])
   return dict(output=[dict(type='message',content=[dict(type='output_text',text='Изменения — после подтверждения.')])])
  w.model_request=model;job=dict(id=1,chat_id=-1,request_text='Напомни договоренности',tool_trace=[])
  with patch.dict(sys.modules,self.modules()):answer,trace=a.answer(w,job,[])
  self.assertIn('подтверждения',answer);self.assertTrue(any(t['name']=='read_agreements' for t in trace))
  self.assertTrue(any(x.get('type')=='reasoning' for x in bodies[1]['input']))
  self.assertFalse(any('execute' in t['name'] or 'write' in t['name'] for t in a.tools()))
 def modules(self):
  p=types.ModuleType('business_agents');p.conversation=types.SimpleNamespace(tools=lambda _:[])
  data=types.ModuleType('business_agents.data');data.Data=lambda *args:object()
  marker=types.ModuleType('china_loss_control');marker.marker=lambda _:{}
  return {'business_agents':p,'business_agents.data':data,'china_loss_control':marker}
 def test_growth_reads_memory_and_forces_verified_tool(self):
  w=W();calls=[];snapshot=dict(experiences=[dict(event_id='negative',business_outcome='negative')],recent_changed_nm_ids=[100]);scan=dict(status='complete',rows=[],memory_used=True,wb_writes=0)
  def model(body):
   calls.append(copy.deepcopy(body))
   if len(calls)==1:return dict(output=[dict(type='function_call',name='get_growth_candidates',arguments=json.dumps(dict(kind='raise',days=3)),call_id='grow')])
   return dict(output=[dict(type='message',content=[dict(type='output_text',text='Недавнее изменение: повторно повышать рано.')])])
  w.model_request=model;job=dict(id=1,chat_id=-1,request_text='Можно повысить ставки?',tool_trace=[])
  import china_growth_candidates
  with patch.dict(sys.modules,self.modules()),patch('china_experience.decision_context',return_value=snapshot),patch.object(china_growth_candidates,'collect',return_value=scan) as collect:
   _,trace=a.answer(w,job,[])
  self.assertEqual(calls[0]['tool_choice'],dict(type='function',name='get_growth_candidates'))
  self.assertIn('negative',calls[0]['input'][0]['content']);self.assertEqual(collect.call_count,1)
  self.assertTrue(next(t for t in trace if t['name']=='get_growth_candidates')['result']['memory_used'])
 def test_model_cannot_skip_candidate_calculation(self):
  w=W();w.model_request=lambda _:dict(output=[dict(type='message',content=[dict(type='output_text',text='Поднимем ставку до 99.')])])
  with patch.dict(sys.modules,self.modules()):answer,_=a.answer(w,dict(id=1,chat_id=-1,request_text='Поднять ставки?',tool_trace=[]),[])
  self.assertIn('Подбор не завершён',answer);self.assertNotIn('99',answer)
 def test_source_summaries_mark_truncation(self):
  v=a.copy_summary(dict(rows=list(range(30)),note='period23Sep22Oct'));self.assertEqual(v['rows_total'],30);self.assertEqual(len(v['rows']),20);self.assertTrue(v['truncated'])

if __name__=='__main__':unittest.main()
