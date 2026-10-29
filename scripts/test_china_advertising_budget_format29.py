import unittest,copy,base64,hashlib,types
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from china_budget_reserve import apply
import china_budget_replace29 as r
from china_daily_ad_actions import handle,BIND
from china_loss_control import PLAN,APPROVAL
class Fake:
 def __init__(self):self.data={};self.bot='offline';self.now=datetime.now(timezone.utc)
 def get(self,k):return copy.deepcopy(self.data.get(k))
 def put(self,k,v):self.data[k]=copy.deepcopy(v)
 def create(self,k,v):
  if k in self.data:return False
  self.put(k,v);return True
 def save(self,k,v,insert=False):return self.create(k,v) if insert else self.put(k,v)
 def tg(self,name,body):return {'id':r.BOT}
def bundle(spend=500,balance=120,amount=10000):
 return {'day':r.DAY,'days':['2026-10-26','2026-10-27','2026-10-28'],'source_observed_at':'dated fixture','campaigns':[{'id':12,'status':9,'name':'Synthetic campaign','balance':balance,'period':{'spend':spend,'amount':amount},'last':{'spend':300,'amount':5000},'current_articles':[{'nm':1},{'nm':2}]}]}
class ReserveTests(unittest.TestCase):
 def test_average_whole_campaign_not_maxday_or_sku(self):
  b=bundle();b['campaigns'][0]['current_period']={'spend':1,'amount':1}
  c=apply(b)['campaigns'][0];self.assertEqual(c['budget_reference_need'],500);self.assertEqual(c['budget_average_daily'],500/3)
  self.assertEqual(c['budget_action']['amount_cny'],400);self.assertEqual(c['budget_action']['nm_ids'],[1,2]);self.assertNotIn('примерно',c['budget_short_note'])
 def test_unknown_profit_model_does_not_block_cash_reserve(self):
  self.assertIsNotNone(apply(bundle())['campaigns'][0]['budget_action'])
 def test_no_gap_hides_row_even_when_high_drr(self):
  c=apply(bundle(50,100,100))['campaigns'][0];self.assertFalse(c['budget_review_required']);self.assertIsNone(c['budget_action'])
 def test_high_completed_campaign_drr_has_explicit_reason(self):
  c=apply(bundle(amount=1000))['campaigns'][0];self.assertTrue(c['budget_review_required']);self.assertIsNone(c['budget_action']);self.assertIn('50,00%',c['budget_short_note'])
 def test_zero_orders_are_not_zero_drr(self):
  c=apply(bundle(amount=0))['campaigns'][0];self.assertIn('не определена',c['budget_short_note']);self.assertIsNone(c['budget_action'])
 def test_minimum_and_rounding(self):
  self.assertEqual(apply(bundle(101,100))['campaigns'][0]['budget_action']['amount_cny'],100)
  self.assertEqual(apply(bundle(101,100),125)['campaigns'][0]['budget_action']['amount_cny'],150)
 def test_float_noise_does_not_add_extra_rounding_step(self):
  self.assertEqual(apply(bundle(500.0000000000001,100))['campaigns'][0]['budget_action']['amount_cny'],400)
 def test_missing_source_keeps_explicit_unknown_row(self):
  c=apply(bundle(spend=None))['campaigns'][0];self.assertTrue(c['budget_review_required']);self.assertIsNone(c['budget_action'])
 def test_inactive_not_funded(self):
  b=bundle();b['campaigns'][0]['status']=11;self.assertFalse(apply(b)['campaigns'][0]['budget_review_required'])
 def test_input_not_mutated(self):
  b=bundle();before=copy.deepcopy(b);apply(b);self.assertEqual(b,before)
class ReplacementTests(unittest.TestCase):
 def fixture(self):
  io=Fake();io.put(r.INPUT,dict(day=r.DAY,chat_id=r.CHAT,bot_id=r.BOT,owner_id=5122667182,old_message_id=485,wb_writes=0,status='owner_approved',authorization='owner_codex_replace_budget29',balances_key='balancefixture',campaigns_key='campaignfixture'))
  io.put('balancefixture',dict(observed_at='2026-10-29T06:18:49+00:00',data={'adverts':[{'advertId':12,'total':120,'currency':'CNY'}]}))
  io.put('campaignfixture',dict(rows=[{'id':12,'status':9,'currency':'CNY','nm_settings':[{'nm_id':1},{'nm_id':2}]}]))
  art=dict(day=r.DAY,status='frozen',bundle=bundle(),files=[]);delivery=dict(status='delivered',parts=[])
  for kind,mid in [('drr:001',484),('budgets:001',485)]:
   raw=('old-'+kind).encode();art['files'].append(dict(kind=kind,family=kind.split(':')[0],b64=base64.b64encode(raw).decode()))
   delivery['parts'].append(dict(kind=kind,message_id=mid,status='sent',sha256=hashlib.sha256(raw).hexdigest(),receipt={'message_id':mid,'chat':{'id':r.CHAT},'from':{'id':r.BOT}}))
  io.put(r.ART,art);io.put(r.DEL,delivery);io.put(BIND+'485',dict(plan_id='oldbudget',plan_sha256='unused',chat_id=r.CHAT))
  io.put(PLAN+'oldbudget',dict(plan_id='oldbudget',items=[],plan_sha256='unused',report_message_ids=[485]))
  f=dict(kind='budgets:001',family='budgets',page=1,total=1,bytes=b'newpng',actions=apply(bundle())['campaigns'][0]['budget_action'])
  f['actions']=[f['actions']]
  with patch.object(r,'render',return_value=[f]):r.prepare(io)
  return io
 def transport(self,calls,fail=None):
  def post(url,**kwargs):
   name=url.rsplit('/',1)[-1];calls.append(name)
   if fail==name:raise TimeoutError()
   result={'chat':{'id':r.CHAT},'from':{'id':r.BOT},'message_id':900,'date':int(datetime.now(timezone.utc).timestamp())} if name=='sendPhoto' else True
   if name=='deleteMessage':self.assertEqual(kwargs['json'],{'chat_id':r.CHAT,'message_id':485})
   if name not in ['sendPhoto','deleteMessage']:raise AssertionError('Unapproved transport')
   return types.SimpleNamespace(json=lambda:{'ok':True,'result':result},ok=True)
  return post
 def job(self,io,mid=900,text='делай'):
  return dict(id=777,update_id=123,sender_id=99,chat_id=r.CHAT,created_at=(io.now+timedelta(seconds=2)).isoformat(),request_text=text,tool_trace=[dict(name='china_saved_question',bot_id=r.BOT,reply_message_id=mid,message_id=1000)])
 def test_send_before_delete_preserves_ad_and_binds_delai(self):
  io=self.fixture();calls=[];oldad=io.get(r.ART)['files'][0]
  with patch.object(r.requests,'post',self.transport(calls),create=True):result=r.apply(io)
  self.assertEqual(calls,['sendPhoto','deleteMessage']);self.assertEqual(result['status'],'completed')
  self.assertEqual(io.get(r.ART)['files'][0],oldad);self.assertEqual([p['message_id'] for p in io.get(r.DEL)['parts']],[484,900])
  self.assertEqual(io.get(r.ROOT+':before_delivery')['parts'][1]['message_id'],485)
  self.assertTrue(io.get(PLAN+'oldbudget')['invalidated_at'])
  with patch('china_group_permissions.allowed',return_value=True):
   reply,trace=handle(io,self.job(io));self.assertEqual(len(trace),1)
  approved=io.get(APPROVAL+'777');self.assertEqual(approved['reply_message_id'],900)
  plan=io.get(PLAN+io.get(BIND+'900')['plan_id']);self.assertEqual(plan['items'][0]['amount_cny'],400)
  with patch.object(r.requests,'post',side_effect=AssertionError('duplicate'),create=True):self.assertEqual(r.apply(io)['status'],'completed')
 def test_send_timeout_never_deletes_or_repeats_photo(self):
  io=self.fixture();calls=[]
  with patch.object(r.requests,'post',self.transport(calls,'sendPhoto'),create=True):
   with self.assertRaises(RuntimeError):r.apply(io)
   with self.assertRaises(RuntimeError):r.apply(io)
  self.assertEqual(calls,['sendPhoto']);self.assertEqual(io.get(r.DEL)['parts'][1]['message_id'],485)
 def test_delete_timeout_never_repeats_send_or_delete(self):
  io=self.fixture();calls=[]
  with patch.object(r.requests,'post',self.transport(calls,'deleteMessage'),create=True):
   with self.assertRaises(RuntimeError):r.apply(io)
   with self.assertRaises(ValueError):r.apply(io)
  self.assertEqual(calls,['sendPhoto','deleteMessage'])
 def test_expired_new_plan_rejected(self):
  io=self.fixture();calls=[]
  with patch.object(r.requests,'post',self.transport(calls),create=True):r.apply(io)
  k=PLAN+io.get(BIND+'900')['plan_id'];p=io.get(k);p['expires_at']=(io.now-timedelta(seconds=1)).isoformat();io.put(k,p)
  with patch('china_group_permissions.allowed',return_value=True):
   reply,trace=handle(io,self.job(io));self.assertIn('устарел',reply);self.assertEqual(trace,[])
 def test_tampered_hash_rejected(self):
  io=self.fixture();calls=[]
  with patch.object(r.requests,'post',self.transport(calls),create=True):r.apply(io)
  b=io.get(BIND+'900');b['plan_sha256']='tampered';io.put(BIND+'900',b)
  with patch('china_group_permissions.allowed',return_value=True):
   with self.assertRaises(ValueError):handle(io,self.job(io))
 def test_old_png_approval_is_revoked(self):
  io=self.fixture();calls=[]
  with patch.object(r.requests,'post',self.transport(calls),create=True):r.apply(io)
  # Old real plans have a valid hash; invalidation is the reason to reject.
  p=io.get(PLAN+'oldbudget');p.update(plan_sha256=r.digest([]),chat_id=r.CHAT,expires_at=(io.now+timedelta(hours=1)).isoformat());io.put(PLAN+'oldbudget',p)
  b=io.get(BIND+'485');b['plan_sha256']=p['plan_sha256'];io.put(BIND+'485',b)
  with patch('china_group_permissions.allowed',return_value=True):
   reply,trace=handle(io,self.job(io,485));self.assertIn('отозван',reply);self.assertEqual(trace,[])
if __name__=='__main__':unittest.main()
