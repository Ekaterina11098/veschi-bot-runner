import base64,copy,hashlib,sys,types,unittest
from unittest.mock import patch
try:import requests
except ModuleNotFoundError:sys.modules['requests']=types.SimpleNamespace(Timeout=TimeoutError,ConnectionError=ConnectionError)
import china_morning_correction27_replace as r
from china_daily_ad_actions import execute
from test_china_advertising_v2 import Fake

class ReplacementTests(unittest.TestCase):
 def fixture(self):
  io=Fake();io.bot='offline';io.tg=lambda name,body:dict(id=r.BOT) if name=='getMe' else dict(user={'id':body['user_id']},status='administrator')
  io.put(r.INPUT,dict(day=r.DAY,chat_id=r.CHAT,bot_id=r.BOT,owner_id=r.OWNER,wb_writes=0,authorization='owner_explicit_request_in_codex_2026-10-27',edit_message_ids=[312,313],delete_message_ids=[314],bundle={'day':r.DAY},status='approved_after_visual_check'))
  oldfiles=[];parts=[];pages=[]
  for i,kind in enumerate(['drr:001','budgets:001']):
   old=b'old'+bytes([i]);family=kind.split(':')[0];mid=312+i
   oldfiles.append(dict(kind=kind,b64=base64.b64encode(old).decode()))
   receipt=dict(message_id=mid,chat={'id':r.CHAT},**{'from':{'id':r.BOT}})
   parts.append(dict(kind=kind,message_id=mid,sha256=hashlib.sha256(old).hexdigest(),receipt=receipt,status='sent'))
   io.put(r.BIND+str(mid),dict(plan_id='old',plan_sha256='oldhash',chat_id=r.CHAT,family=family))
   pages.append(dict(kind=kind,family=family,page=1,total=1,bytes=b'new'+bytes([i]),actions=[]))
  io.put(r.ART,dict(day=r.DAY,status='frozen',files=oldfiles,bundle={}))
  io.put(r.DEL,dict(status='delivered',parts=parts))
  io.put(r.LOSS,dict(status='delivered',parts=[dict(message_id=314,receipt=dict(chat={'id':r.CHAT},**{'from':{'id':r.BOT}}))]))
  with patch.object(r,'render',return_value=pages):r.prepare(io)
  return io
 def test_exact_two_edits_and_one_delete_preserve_identity_and_binding(self):
  io=self.fixture();calls=[]
  def post(url,**kw):
   calls.append((url,kw))
   if url.endswith('/editMessageMedia'):
    mid=int(kw['data']['message_id']);result=dict(message_id=mid,edit_date=1793080800,chat={'id':r.CHAT},**{'from':{'id':r.BOT}})
   elif url.endswith('/deleteMessage'):
    self.assertEqual(kw['json']['message_id'],314);result=True
   else:raise AssertionError('Unapproved Telegram or marketplace operation')
   return types.SimpleNamespace(json=lambda:dict(ok=True,result=result))
  with patch.object(r.requests,'post',post,create=True):result=r.apply(io)
  self.assertEqual(result['status'],'completed');self.assertEqual(len(calls),3)
  self.assertEqual([p['message_id'] for p in io.get(r.DEL)['parts']],[312,313])
  self.assertEqual(io.get(r.ART)['owner_revision'],r.ROOT)
  self.assertEqual(io.get(r.DEL)['status'],'delivered')
  self.assertEqual(io.get(r.BIND+'312')['owner_revision'],r.ROOT)
  self.assertIn('visible_from',io.get(r.PLAN+io.get(r.BIND+'312')['plan_id']))
  self.assertTrue(io.get(r.LOSS)['retracted_at'])
  with patch.object(r.requests,'post',side_effect=AssertionError('duplicate'),create=True):self.assertEqual(r.apply(io)['status'],'completed')
 def test_timeout_never_repeats_edit(self):
  io=self.fixture()
  with patch.object(r.requests,'post',side_effect=TimeoutError,create=True) as post:
   with self.assertRaises(RuntimeError):r.apply(io)
   with self.assertRaisesRegex(ValueError,'uncertain'):r.apply(io)
   self.assertEqual(post.call_count,1)
 def test_wrong_delete_scope_rejected(self):
  io=self.fixture();p=io.get(r.INPUT);p['delete_message_ids']=[315]
  with self.assertRaises(ValueError):r.validate_input(p)
 def test_approval_before_updated_image_cannot_execute(self):
  io=Fake();io.validate_owner=lambda _:None
  with self.assertRaisesRegex(ValueError,'predates'):
   execute(io,dict(created_at='2026-10-27T05:00:00Z'),dict(visible_from='2026-10-27T06:00:00Z'))

if __name__=='__main__':unittest.main()

