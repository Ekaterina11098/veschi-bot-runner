import copy,json,unittest
from unittest.mock import patch
from datetime import datetime,timezone
import china_codex_ad_review as review
from china_loss_control import CHAT,BOT,PLAN,APPROVAL,digest
from china_daily_ad_actions import handle,execute,BIND

class Store:
 def __init__(self):self.data={};self.now=datetime.now(timezone.utc);self.token='test'
 def get(self,k):return copy.deepcopy(self.data.get(k))
 def save(self,k,v,insert=False):
  if insert and k in self.data:return False
  self.data[k]=copy.deepcopy(v);return True
 def create(self,k,v):return self.save(k,v,True)
 def put(self,k,v):return self.save(k,v)
 def validate_owner(self,a):pass

class ReviewTests(unittest.TestCase):
 def setUp(self):
  self.w=Store();self.job=dict(id=9001,sender_id=307200273,chat_id=CHAT)
  self.item=dict(id='42:101',kind='ad_set_bid',campaign_id=42,nm_id=101,article='SKU',placement='search',old_minor=30,target_minor=28)
  self.result=dict(status='reviewed',actions=[self.item],rows=[],days=['2026-11-07','2026-11-08','2026-11-09'],wb_writes=0)
 def prepared(self):
  with patch.object(review,'review',return_value=copy.deepcopy(self.result)):
   return review.prepare(self.w,self.job,dict(kind='review_advertising',campaign_ids=[42]),io=object())
 def confirmation(self,mid=600):
  return dict(id=9002,update_id=5,sender_id=307200273,chat_id=CHAT,request_text='Сделай все',created_at=datetime.now(timezone.utc).isoformat(),tool_trace=[dict(name='china_saved_question',bot_id=BOT,message_id=601,reply_message_id=mid)])
 def test_worker_collects_then_uses_exact_plan_without_second_model(self):
  import china_codex_cloud as c
  from test_china_codex_cloud import inbox,FakeDB,FakeWorker
  i=inbox();db=FakeDB(i);worker=FakeWorker(db,dict(kind='review_advertising',campaign_ids=[42]))
  self.assertEqual(worker.process(c.ROOT+'inbox:231',i),'collecting')
  self.assertIsNone(db.get(c.ROOT+'outbox:231'));self.assertEqual(db.get(c.ROOT+'data_request:231')['kind'],'review_advertising')
  db.values[c.ROOT+'analytics:231']=dict(status='calculated',kind='review_advertising',read_round=1,result=dict(status='reviewed',answer='Точный проверенный план'))
  current=db.get(c.ROOT+'inbox:231')
  self.assertEqual(worker.process(c.ROOT+'inbox:231',current),'ready')
  self.assertEqual(worker.calls,1);self.assertEqual(db.get(c.ROOT+'outbox:231')['answer'],'Точный проверенный план')
 def test_no_model_supplied_actions(self):
  with self.assertRaises(ValueError):review.request(dict(kind='review_advertising',campaign_ids=[42],items=[self.item]))
 def test_prepare_is_not_consent(self):
  self.prepared();self.assertIsNone(handle(self.w,self.confirmation()));self.assertFalse(any(k.startswith(APPROVAL)for k in self.w.data))
 def test_bound_confirmation_only_records_approval(self):
  r=self.prepared();review.bind(self.w,9001,[600],r['answer'])
  with patch('china_group_permissions.allowed',return_value=True):answer=handle(self.w,self.confirmation())
  self.assertIsNotNone(answer);a=self.w.get(APPROVAL+'9002');self.assertEqual(a['reply_message_id'],600);self.assertEqual(a['plan_sha256'],digest([self.item]))
  self.assertIsNone(handle(self.w,self.confirmation(599)))
 def test_changed_text_hash_and_revocation(self):
  r=self.prepared()
  with self.assertRaises(ValueError):review.bind(self.w,9001,[600],r['answer']+'changed')
  review.bind(self.w,9001,[600],r['answer']);p=self.w.get(PLAN+r['plan_id']);p['invalidated_at']='now';self.w.put(PLAN+r['plan_id'],p)
  with patch('china_group_permissions.allowed',return_value=True):answer=handle(self.w,self.confirmation())
  self.assertIn('отозван',answer[0]);self.assertIsNone(self.w.get(APPROVAL+'9002'))
 def test_empty_review_has_no_executable_plan(self):
  self.result['actions']=[];r=self.prepared();self.assertIsNone(r['plan_id']);review.bind(self.w,9001,[600],r['answer']);self.assertIsNone(self.w.get(BIND+'600'))
 def test_native_execution_and_replay_write_once(self):
  r=self.prepared();review.bind(self.w,9001,[600],r['answer'])
  with patch('china_group_permissions.allowed',return_value=True):handle(self.w,self.confirmation())
  p=self.w.get(PLAN+r['plan_id']);a=self.w.get(APPROVAL+'9002')
  campaign=dict(id=42,currency='CNY',status=9,bid_type='manual',settings=dict(payment_type='cpc'),nm_settings=[dict(nm_id=101,bids_kopecks={'search':30})]);writes=[]
  class Response:
   ok=True;content=b'{}'
   def __init__(self,value):self.value=value
   def json(self):return copy.deepcopy(self.value)
  def request(method,url,**kw):
   if '/api/advert/v2/adverts?'in url:return Response(dict(adverts=[campaign]))
   if url.endswith('/api/advert/v1/bids/min'):return Response(dict(bids=[dict(nm_id=101,bids=[dict(type='search',currency='CNY',value=28)])]))
   if method=='PATCH'and url.endswith('/api/advert/v1/bids'):
    writes.append(kw['json']);campaign['nm_settings'][0]['bids_kopecks']['search']=28;return Response({})
   raise AssertionError('Unexpected network '+method+' '+url)
  with patch('requests.request',side_effect=request),patch('time.sleep'),patch('china_execution_notice.deliver_result'):
   first=execute(self.w,a,p);second=execute(self.w,a,p)
  self.assertEqual(len(writes),1);self.assertEqual(first['items'][0]['status'],'verified');self.assertEqual(second['items'][0]['status'],'verified')

if __name__=='__main__':unittest.main()
