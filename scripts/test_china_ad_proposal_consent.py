import copy,sys,types,unittest
from datetime import datetime,timezone
from unittest.mock import patch
import china_ad_proposal_consent as c
import china_free_ads as f
REQUEST='china_agent:new_ad_report_request:v1:'
class W:
 def __init__(self):self.now=datetime.now(timezone.utc);self.values={}
 def get(self,k):return copy.deepcopy(self.values.get(k))
 def save(self,k,v,insert=False):
  if insert and k in self.values:return False
  self.values[k]=copy.deepcopy(v);return True
 def catalog(self):return [(101,'59-Noel-grey'),(102,'63-Noel-blue'),(103,'63-Zont-other'),(104,'144-Samira-brown'),(105,'99-other')]
 def db(self,*a,**kw):return [{'payload':{'answer':'| Кандидат | Экономика |\n|---|---|\n| 59 — Noel серая | +10 |\n| 63 — Noel синяя | +10 |\n| 144 — Samira коричневая | +10 |\n| 99 — Other | +10 |\n**Первая очередь для подготовки теста: 59, 63, 144**'}}]
def job(jid,text,reply=737):return dict(id=jid,update_id=jid,chat_id=c.CHAT,sender_id=307200273,created_at=datetime.now(timezone.utc).isoformat(),request_text=text,tool_trace=[dict(name='china_saved_question',bot_id=c.BOT,message_id=jid+1000,reply_message_id=reply)])
class Tests(unittest.TestCase):
 def setUp(self):
  new=types.ModuleType('china_new_ads');new.REQUEST=REQUEST;new.BIND='new_bind:';new.handle=lambda *a:('Точный план принят',[])
  permissions=types.ModuleType('china_group_permissions');permissions.allowed=lambda *a:True
  self.p=patch.dict(sys.modules,{'china_new_ads':new,'china_group_permissions':permissions});self.p.start();self.addCleanup(self.p.stop)
 def setup_question(self):
  w=W();qjob=job(263,'Если ещё нет, запусти на них рекламу');text=f.handle(w,qjob);c.bind(w,263,[800],text);return w,text
 def test_launch_without_plan_asks_only_then_yes_creates_preparation(self):
  w,text=self.setup_question();self.assertIn('Подготовить',text);self.assertFalse(any(k.startswith(REQUEST)for k in w.values))
  reply=f.handle(w,job(266,'Да, подготовь',800));r=w.get(REQUEST+'266')
  self.assertEqual([101,102,104],r['nm_ids']);self.assertIs(r['grants_action_permission'],False);self.assertIn('отдельное подтверждение',reply)
  self.assertFalse(any('approval' in k or 'execution' in k for k in w.values))
 def test_explicit_prepare_does_not_ask_redundant_question(self):
  w=W();result=f.handle(w,job(1,'Подготовь предложение для рекламы 59-Noel-grey'))
  self.assertIn('Подготовлю',result);self.assertEqual([101],w.get(REQUEST+'1')['nm_ids']);self.assertFalse(w.get(c.QUESTION+'1'))
 def test_no_declines_and_cannot_later_become_yes(self):
  w,text=self.setup_question();self.assertIn('не готовлю',f.handle(w,job(266,'Нет',800)))
  self.assertIn('уже получен',f.handle(w,job(267,'Да',800)));self.assertFalse(any(k.startswith(REQUEST)for k in w.values))
 def test_duplicate_yes_does_not_queue_second_job(self):
  w,text=self.setup_question();f.handle(w,job(266,'Да',800));f.handle(w,job(266,'Да',800));f.handle(w,job(267,'Да',800))
  self.assertEqual(1,sum(k.startswith(REQUEST)for k in w.values))
 def test_unrelated_yes_never_prepares(self):
  w,text=self.setup_question();self.assertIsNone(f.handle(w,job(266,'Да',801)));self.assertFalse(any(k.startswith(REQUEST)for k in w.values))
 def test_expired_question_not_accepted(self):
  w,text=self.setup_question();w.values[c.QUESTION+'263']['expires_at']='2000-01-01T00:00:00+00:00'
  self.assertIn('устарело',f.handle(w,job(266,'Да',800)));self.assertFalse(w.get(REQUEST+'266'))
 def test_forward_wrong_actor_and_wrong_chat_rejected(self):
  for case in ('forward','actor','chat'):
   w,text=self.setup_question();j=job(266,'Да',800)
   if case=='forward':j['tool_trace'][0]['forwarded']=True
   if case=='actor':j['sender_id']=123
   if case=='chat':j['chat_id']=1
   f.handle(w,j);self.assertFalse(w.get(REQUEST+'266'))
 def test_modified_answer_not_bound(self):
  w=W();text=c.ask(w,job(263,'Запусти рекламу'),[101])
  with self.assertRaises(ValueError):c.bind(w,263,[800],text+'Changed')
 def test_unclear_reply_does_not_prepare_or_launch(self):
  w,text=self.setup_question();self.assertIn('только подготовку',f.handle(w,job(266,'Да, запускай и пополни 1000',800)));self.assertFalse(w.get(REQUEST+'266'))
 def test_current_ready_plan_still_uses_existing_executor(self):
  w=W();w.values['new_bind:800']={'plan_id':'exact'}
  self.assertEqual('Точный план принят',f.handle(w,job(1,'Делай',800)))
 def test_real_pavel_yes_with_twenty_refinement_is_preparation(self):
  w,text=self.setup_question();reply=f.handle(w,job(266,'Да. Если можешь найти больше 5 найди. Лучше около 20 найти если это возможно',800));r=w.get(REQUEST+'266')
  self.assertEqual(20,r['maximum_count']);self.assertEqual([],r['nm_ids']);self.assertEqual([101,102,104],r['seed_nm_ids']);self.assertIn('20',reply);self.assertFalse(r['grants_action_permission'])
  self.assertFalse(any('approval' in k for k in w.values))
 def test_yes_does_not_override_negative_or_large_scope(self):
  for text in ('Да, но не готовь предложение','Да. Найди около 100 товаров'):
   w,_=self.setup_question();f.handle(w,job(266,text,800));self.assertFalse(w.get(REQUEST+'266'))
if __name__=='__main__':unittest.main()

