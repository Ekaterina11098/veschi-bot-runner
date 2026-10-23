import copy,unittest,sys,types
try:import requests
except ImportError:sys.modules['requests']=types.ModuleType('requests')
from unittest.mock import patch
from datetime import timedelta
import ip_png_apply as m
class Fake:
 def __init__(self,p,a):self.s={m.PLAN:copy.deepcopy(p),m.PLAN+':approval':a};self.calls=[]
 def get(self,k):return copy.deepcopy(self.s.get(k))
 def create(self,k,v):
  if k in self.s:return False
  self.s[k]=copy.deepcopy(v);return True
 def put(self,k,v):self.s[k]=copy.deepcopy(v)
 def identity(self):pass
 def member(self,u):
  if u==0:raise ValueError('Not member')
 def tg(self,*a):return {'chat':{'id':m.CHAT},'message_id':99}
def fixture():
 items=[dict(nm_id=n,campaign_id=m.CID,kind='ad_exclude_sku') for n in sorted(m.TARGETS)]
 b=dict(id=m.CID,currency='RUB',status=9,bid_type='manual',settings={'payment_type':'cpm'},restrictions={'can_change_nms':True},nm_settings=[dict(nm_id=n,bids_kopecks={'recommendations':10500}) for n in sorted(m.TARGETS|{123})])
 p=dict(chat_id=m.CHAT,bot_id=m.BOT,campaign_id=m.CID,return_policy='separate_explicit_decision',items=items,plan_sha256=m.digest(items),message_id=100,before=m.stable(b),expires_at=(m.now()+timedelta(hours=1)).isoformat())
 a=dict(chat_id=m.CHAT,bot_id=m.BOT,reply_message_id=100,plan_sha256=p['plan_sha256'],command='Сделай всё',update_id=8,sender_id=777,input_message_id=101)
 return p,a,b
class Tests(unittest.TestCase):
 def test_technical_failure_does_not_notify(self):
  p,a,b=fixture();io=Fake(p,a)
  with patch.object(m,'current',side_effect=RuntimeError('Source HTTP 429; retry after 3459 seconds')),patch.object(io,'tg') as tg:
   self.assertEqual(m.apply(io,m.PLAN+':approval')['status'],'blocked');tg.assert_not_called()
 def test_reordering_is_not_a_setting_change(self):
  p,a,b=fixture();b['nm_settings'].reverse();after=copy.deepcopy(b);after['nm_settings']=[n for n in b['nm_settings'] if n['nm_id'] not in m.TARGETS]
  with patch.object(m,'current',side_effect=[{m.CID:b},{m.CID:after}]),patch.object(m,'http',return_value={}) as h:
   self.assertEqual(m.apply(Fake(p,a),m.PLAN+':approval')['status'],'verified');self.assertEqual(h.call_count,1)
 def test_resume_retains_failed_attempt(self):
  p,a,b=fixture();io=Fake(p,a);old={'status':'blocked','reason':'ModuleNotFoundError','wb_writes':0};io.s[m.PLAN+':execution']=old.copy();io.s[m.PLAN+':resume_authorization:20261023']={'authorized':True,'approval_update_id':a['update_id'],'plan_sha256':p['plan_sha256']};after=copy.deepcopy(b);after['nm_settings']=[n for n in b['nm_settings'] if n['nm_id'] not in m.TARGETS]
  with patch.object(m,'current',side_effect=[{m.CID:b},{m.CID:after}]),patch.object(m,'http',return_value={}) as h:
   self.assertEqual(m.apply(io,m.PLAN+':approval')['status'],'verified');m.apply(io,m.PLAN+':approval');self.assertEqual(h.call_count,1);self.assertEqual(io.s[m.PLAN+':execution'],old)
 def test_resume_cannot_replay_unknown(self):
  p,a,b=fixture();io=Fake(p,a);io.s[m.PLAN+':execution']={'status':'uncertain','wb_writes':0};io.s[m.PLAN+':resume_authorization:20261023']={'authorized':True,'approval_update_id':a['update_id'],'plan_sha256':p['plan_sha256']}
  with patch.object(m,'current') as read:self.assertEqual(m.apply(io,m.PLAN+':approval')['status'],'uncertain');read.assert_not_called()
 def test_publish_preparation_uses_saved_baseline(self):
  p,a,b=fixture();p['baseline']=b;io=Fake(p,a)
  with patch.object(m,'current') as read:
   self.assertEqual(m.prepare(io,p),m.stable(b));read.assert_not_called()
 def test_delivered_png_not_sent_twice(self):
  p,a,b=fixture();p['delivery_status']='sent';io=Fake(p,a)
  self.assertEqual(m.publish(io)['message_id'],100)
 def test_unknown_png_not_repeated(self):
  p,a,b=fixture();p.pop('message_id');p['delivery_status']='uncertain';io=Fake(p,a)
  self.assertEqual(m.publish(io)['status'],'uncertain')
 def test_exact_single_write_and_duplicate(self):
  p,a,b=fixture();io=Fake(p,a);after=copy.deepcopy(b);after['nm_settings']=[n for n in b['nm_settings'] if n['nm_id'] not in m.TARGETS]
  with patch.object(m,'current',side_effect=[{m.CID:b},{m.CID:after}]),patch.object(m,'http',return_value={}) as h:
   self.assertEqual(m.apply(io,m.PLAN+':approval')['status'],'verified');m.apply(io,m.PLAN+':approval');self.assertEqual(h.call_count,1);self.assertEqual(set(h.call_args.args[3]['nms'][0]['nms']['delete']),m.TARGETS)
 def test_wrong_reply(self):
  p,a,b=fixture();a['reply_message_id']=999
  with self.assertRaises(ValueError):m.apply(Fake(p,a),m.PLAN+':approval')
 def test_wrong_plan(self):
  p,a,b=fixture();p['items'][0]['nm_id']=1007948808
  with self.assertRaises(ValueError):m.validate(p)
 def test_changed_campaign_blocks(self):
  p,a,b=fixture();b['status']=11
  with patch.object(m,'current',return_value={m.CID:b}),patch.object(m,'http') as h:
   self.assertEqual(m.apply(Fake(p,a),m.PLAN+':approval')['status'],'blocked');h.assert_not_called()
 def test_unknown_write_never_repeats(self):
  p,a,b=fixture();io=Fake(p,a)
  with patch.object(m,'current',return_value={m.CID:b}),patch.object(m,'http',side_effect=TimeoutError) as h:
   self.assertEqual(m.apply(io,m.PLAN+':approval')['status'],'uncertain');m.apply(io,m.PLAN+':approval');self.assertEqual(h.call_count,1)
 def test_nonmember(self):
  p,a,b=fixture();a['sender_id']=0
  with self.assertRaises(ValueError):m.apply(Fake(p,a),m.PLAN+':approval')
 def test_expiry(self):
  p,a,b=fixture();p['expires_at']=(m.now()-timedelta(seconds=1)).isoformat()
  with self.assertRaises(ValueError):m.apply(Fake(p,a),m.PLAN+':approval')
if __name__=='__main__':unittest.main()

