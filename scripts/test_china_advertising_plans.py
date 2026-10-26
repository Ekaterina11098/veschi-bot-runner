import unittest,copy,types,sys
from datetime import datetime,timezone
from unittest.mock import patch
import china_advertising_plans as p
from china_loss_control import is_all,digest
class W:
 now=datetime(2026,10,26,14,tzinfo=timezone.utc)
 def __init__(self):self.mem={}
 def get(self,k):return copy.deepcopy(self.mem.get(k))
 def save(self,k,v,insert=False):
  if insert and k in self.mem:return False
  self.mem[k]=copy.deepcopy(v);return True
def modules():
 g=types.ModuleType('china_group_permissions');g.allowed=lambda w,j:j.get('sender_id')==1
 return {'china_group_permissions':g}
def plan(w):
 items=[dict(kind='ad_raise_bid',campaign_id=10,nm_id=100,article='one-bag',placement='recommendations',old_minor=28,target_minor=31)]
 v=dict(plan_id='dialog-ads-7-raise',execution_kind='advertising_dialog_v1',items=items,plan_sha256=digest(items),chat_id=p.CHAT,bot_id=p.BOT,created_at='2026-10-26T13:00:00+00:00',expires_at='2026-10-26T16:00:00+00:00',report_message_ids=[],text='Точный план\nПлан рекламы: dialog-ads-7-raise')
 w.mem[p.P+v['plan_id']]=v;return v
def job(text='Делай'):
 return dict(id=8,update_id=88,sender_id=1,chat_id=p.CHAT,created_at='2026-10-26T14:00:00+00:00',request_text=text,tool_trace=[dict(name='china_saved_question',bot_id=p.BOT,message_id=81,reply_message_id=71)])
class Tests(unittest.TestCase):
 def test_positive_aliases(self):
  for s in ['Делай','давай добавляй','Делай добавляй в рекламу','меняем ставки','давай повышай','Сделай всё']:
   self.assertTrue(is_all(s),s)
 def test_negation_and_unknown_scope_not_consent(self):
  for s in ['Не делай','не добавляй','Давай подумаем','И ставки увеличь где возможно','Делай, но только потом','Делай и удали все РК']:
   self.assertFalse(is_all(s),s)
 def test_unbound_text_cannot_authorize(self):
  with patch.dict(sys.modules,modules()):self.assertIsNone(p.handle(W(),job()))
 def test_plan_binding_and_dedup(self):
  w=W();v=plan(w);p.bind(w,v['text'],71)
  with patch.dict(sys.modules,modules()):
   text,trace=p.handle(w,job('Делай добавляй в рекламу'));self.assertIn('Принято',text)
   again,_=p.handle(w,job());self.assertIn('уже принят',again)
  self.assertEqual(sum(k.startswith(p.A) for k in w.mem),1)
 def test_changed_text_cannot_bind(self):
  w=W();v=plan(w)
  with self.assertRaises(ValueError):p.bind(w,'Изменили цифры\nПлан рекламы: dialog-ads-7-raise',71)
 def test_hash_mismatch_rejected(self):
  w=W();v=plan(w);p.bind(w,v['text'],71);w.mem[p.P+v['plan_id']]['items'][0]['target_minor']=99
  with patch.dict(sys.modules,modules()),self.assertRaises(ValueError):p.handle(w,job())
 def test_expired_plan_not_executed(self):
  w=W();v=plan(w);p.bind(w,v['text'],71);w.now=datetime(2026,10,27,tzinfo=timezone.utc)
  with patch.dict(sys.modules,modules()):text,_=p.handle(w,job())
  self.assertIn('устарел',text);self.assertFalse(any(k.startswith(p.A) for k in w.mem))
 def test_foreign_actor_denied(self):
  w=W();v=plan(w);p.bind(w,v['text'],71);j=job();j['sender_id']=2
  with patch.dict(sys.modules,modules()):text,_=p.handle(w,j)
  self.assertIn('участникам',text);self.assertFalse(any(k.startswith(p.A) for k in w.mem))
 def test_unknown_economics_not_zero(self):
  with self.assertRaises(ValueError):p.economics({},100)
 def test_negative_economics_blocked(self):
  s=dict(products=[dict(nm_id=100,sa_name='one',subject_id=50,finished_orders=10,is_payed=1,total_commission_without_spp_in_sales=20,sales_sum_without_spp=100,price_after_discount=100,price_after_spp=100)],stock=[dict(article='one',stock=100,reserve=0,price=100000)],prices=[dict(nmID=100,currencyIsoCode4217='CNY',sizes=[dict(discountedPrice=100)])],policy=dict(logistics_by_nm={'100':dict(delivery_cny=10)}))
  with self.assertRaises(ValueError):p.economics(s,100)
 def test_uncertain_execution_never_repeated(self):
  w=W();v=plan(w);p.bind(w,v['text'],71)
  a=dict(plan_id=v['plan_id'],plan_sha256=v['plan_sha256'],reply_message_id=71)
  w.validate_owner=lambda a:None
  w.mem[p.E+v['plan_id']]=dict(status='attention',items=[],steps={'0:bid':dict(status='uncertain')})
  mod=types.ModuleType('china_cloud_cost_control');mod.WB=lambda:(_ for _ in ()).throw(AssertionError('WB constructor must not run'))
  with patch.dict(sys.modules,{'china_cloud_cost_control':mod}):self.assertEqual(p.execute(w,a,v)['status'],'attention')
if __name__=='__main__':unittest.main()
