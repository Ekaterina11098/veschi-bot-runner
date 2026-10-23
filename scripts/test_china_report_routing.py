import types,sys,unittest
from unittest.mock import patch,Mock
from conversion_watches import Worker

class Routing(unittest.TestCase):
 def test_general_report_is_not_filtered_as_cost_growth(self):self.check('Пришли отчёт ДРР за 3 дня',False)
 def test_explicit_cost_growth_preserves_approved_handler(self):self.check('Рост стоимости рекламного заказа за 3 дня',True)
 def check(self,text,legacy):
  w=Worker(lambda *a,**kw:[],lambda *a:None);w.config=lambda:dict(chat_id=-1);w.get=lambda _:dict(enabled=True)
  generic=Mock(return_value=('new-report',[]));old=Mock(return_value=('old-trend',[]))
  modules={}
  for name in ['china_new_ads','china_ad_rule','china_loss_control']:
   m=types.ModuleType(name);m.handle=lambda *a:None;modules[name]=m
  m=types.ModuleType('china_ad_cost_png');m.answer=old;modules['china_ad_cost_png']=m
  m=types.ModuleType('china_analytic_dialog');m.answer=generic;modules['china_analytic_dialog']=m
  m=types.ModuleType('business_agents');m.conversation=object();modules['business_agents']=m
  m=types.ModuleType('business_agents.data');m.Data=object;modules['business_agents.data']=m
  job=dict(agent_id='china',chat_id=-1,sender_id=2,request_text=text,tool_trace=[dict(name='china_saved_question')])
  with patch.dict(sys.modules,modules):answer,_=w.saved_question(job,[])
  self.assertEqual(answer,'old-trend' if legacy else 'new-report');self.assertEqual(old.call_count,int(legacy));self.assertEqual(generic.call_count,int(not legacy))

if __name__=='__main__':unittest.main()

