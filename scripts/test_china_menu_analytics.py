import sys,types,unittest
from unittest.mock import patch
import china_menu_analytics as m
class W:
 def __init__(self):self.data={}
 def get(self,k):return self.data.get(k)
 def save(self,k,v,insert=False):
  if insert and k in self.data:return False
  self.data[k]=v;return True
class TestMenu(unittest.TestCase):
 def test_selected_directions(self):
  self.assertEqual(m.directions(m.CANDIDATES+'Новые товары для добавления. Новые повышения ставок.'),['add','raise'])
  with self.assertRaises(ValueError):m.directions('Не выбран фильтр')
 def test_history_identity_and_missing(self):
  raw={'data':[{'product':{'nmId':455,'vendorCode':'455'},'history':[{'date':'2026-11-10','openCount':100,'cartCount':4,'orderCount':2}]}]}
  rows=m.history_rows(raw,455,'2026-11-01','2026-11-10','source','now')
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['metrics']['orders'],2)
  with self.assertRaises(ValueError):m.history_rows(raw,143,'2026-11-01','2026-11-10','source','now')
  del raw['data'][0]['history'][0]['openCount']
  with self.assertRaises(ValueError):m.history_rows(raw,455,'2026-11-01','2026-11-10','source','now')
 def test_prepare_once_no_promise(self):
  w=W();job={'id':303,'chat_id':-1004342917488};inbox={'request_text':m.CANDIDATES+'Новые повышения ставок.','input_message_id':918,'thread_id':'thread'}
  with patch.object(m,'candidate',return_value='Проверенный результат')as work:
   self.assertTrue(m.prepare(w,job,inbox));self.assertTrue(m.prepare(w,job,inbox));self.assertEqual(work.call_count,1)
  out=w.get(m.ROOT+'outbox:303');self.assertEqual(out['answer'],'Проверенный результат');self.assertEqual(out['model_calls'],0)
 def test_blocker_is_terminal_truth_not_ack(self):
  w=W();job={'id':303,'chat_id':-1004342917488};inbox={'request_text':m.CANDIDATES+'Новые повышения ставок.','input_message_id':918,'thread_id':'thread'}
  with patch.object(m,'candidate',side_effect=ValueError('Нет точной ставки')):m.prepare(w,job,inbox)
  self.assertIn('Готового результата нет',w.get(m.ROOT+'outbox:303')['answer']);self.assertEqual(w.get('china_agent:menu_analytics:v1:303')['status'],'blocked')
 def test_unrelated_dialogue_not_intercepted(self):
  w=W();self.assertFalse(m.prepare(w,{}, {'request_text':'Сколько заказов?'}));self.assertFalse(w.data)
 def test_candidate_plan_keeps_only_selected_directions(self):
  w=W();job={'id':303,'chat_id':-1004342917488,'sender_id':5122667182}
  actions={k:dict(id=k,direction=k,placement='recommendations',kind='ad_add_sku'if k=='add'else'ad_set_bid',campaign_id=123,nm_id=i+1,article='item'+str(i+1),target_minor=30,old_minor=28 if k=='raise'else 32)for i,k in enumerate(m.LABELS)}
  bundle={'days':['2026-11-08','2026-11-09','2026-11-10'],'recommendation_directions':{k:dict(status='checked',rows=[{'ready':True,'action':a}],count=1)for k,a in actions.items()},'campaigns':[{'id':123,'focus':[{'action':a,'nm':a['nm_id'],'article':a['article'],'economics':{'seller_price_cny':100,'own_cogs_rub':20}}for a in actions.values()],'attention':[]}]}
  def module(**values):return types.SimpleNamespace(**values)
  rendered=[]
  def render(b):
   rendered.append(b);return [{'family':'drr','bytes':b'PNG'}]
  from contextlib import nullcontext
  checks=[]
  class FakeIO:pass
  mods={'china_analytic_dialog':module(reading=nullcontext),'china_loss_execute':module(IO=FakeIO),'china_advertising_v2':module(prepare=lambda io,day:bundle,http=lambda *args:{'adverts':[{'id':123,'currency':'CNY','status':9,'nm_settings':[{'nm_id':2,'bids_kopecks':{'recommendations':28}}]}]}),'china_advertising_growth':module(validate_raise=lambda io,a,c:checks.append(a['id'])),'china_advertising_full_growth':module(validate_addition=lambda io,a,c:checks.append(a['id'])),'china_advertising_v2_png':module(render=render),'china_loss_control':module(PLAN='plan:',digest=lambda x:str(len(x))),'china_morning_rules_review':module(enabled=lambda io:True),'china_table_png':module(KEY='table:',PREFIX='PNG:')}
  mods['china_morning_readiness']=module(current_prices=lambda *a:dict(rows=[dict(nm_id=i,article='item'+str(i),seller_price=100)for i in (1,2)]),published_stock=lambda *a:dict(amounts={'1':5,'2':5}))
  mods['china_moysklad_read']=module(read_stock=lambda *a:dict(coverage_complete=True,rows=[dict(article='item'+str(i),price=2000,stock=5,reserve=0)for i in (1,2)]))
  with patch.dict(sys.modules,mods):answer=m.candidate(w,job,m.CANDIDATES+'Новые товары для добавления. Новые повышения ставок.')
  self.assertEqual({a['id']for a in w.get('plan:dialog-menu-303')['items']},{'add','raise'})
  self.assertEqual(rendered[0]['recommendation_directions']['reduce']['rows'],[])
  self.assertEqual(w.get('table:303')['parts'][0],answer)
  self.assertEqual(w.get('china_agent:codex_ad_review:v1:303')['answer'],answer)
  self.assertEqual(set(checks),{'add','raise'})
 def test_zero_ready_actions_is_brief_and_discloses_missing_economics(self):
  from contextlib import nullcontext
  w=W();job={'id':304,'chat_id':-1004342917488};bundle={'recommendation_directions':{k:{'status':'checked','rows':[]}for k in m.LABELS},'full_cabinet_growth_review':{'missing_economics':{'1':'missing'}}}
  class FakeIO:pass
  mod=lambda **values:types.SimpleNamespace(**values)
  def forbidden(*args):raise AssertionError('No empty diagnostic PNG')
  modules={'china_analytic_dialog':mod(reading=nullcontext),'china_loss_execute':mod(IO=FakeIO),'china_advertising_v2':mod(prepare=lambda *args:bundle),'china_advertising_v2_png':mod(render=forbidden),'china_morning_rules_review':mod(enabled=lambda io:True),'china_loss_control':mod(PLAN='plan:',digest=str)}
  with patch.dict(sys.modules,modules):answer=m.candidate(w,job,m.CANDIDATES+'Новые повышения ставок.')
  self.assertIn('не хватает данных собственной экономики',answer);self.assertNotIn('все товары не подходят',answer)
  self.assertEqual(w.get('china_agent:menu_analytics:v1:304')['report_kind'],'no_ready_actions')
if __name__=='__main__':unittest.main()