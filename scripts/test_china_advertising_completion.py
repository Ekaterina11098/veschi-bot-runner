import ast,copy,hashlib,json,unittest
from pathlib import Path
from datetime import datetime,timezone
CHAT=-1004342917488;BOT=8780468043
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
tree=ast.parse(Path(__file__).with_name('china_execution_notice.py').read_text(encoding='utf8'))
ns=dict(copy=copy,datetime=datetime,timezone=timezone,CHAT=CHAT,BOT=BOT,PREFIX='china_agent:daily_ad_result:v2:')
for node in tree.body:
 if isinstance(node,ast.FunctionDef):exec(compile(ast.Module(body=[node],type_ignores=[]),'notice','exec'),ns)
deliver=ns['deliver_result']
class IO:
 def __init__(self):self.data={};self.sent=[];self.fail=False
 def get(self,k):return copy.deepcopy(self.data.get(k))
 def create(self,k,v):
  if k in self.data:return False
  self.data[k]=copy.deepcopy(v);return True
 def put(self,k,v):self.data[k]=copy.deepcopy(v)
 def tg(self,method,body):
  self.sent.append((method,body))
  if self.fail:raise TimeoutError()
  return dict(message_id=1009,chat=dict(id=CHAT),**{'from':dict(id=BOT)})
def fixture():
 item=dict(id='a',kind='ad_add_sku',campaign_id=1,nm_id=50,article='50',subject_id=50,placement='search',target_minor=28)
 before=dict(id=1,status=9,settings={'name':'test'},nm_settings=[dict(nm_id=1,bids_kopecks={'search':30})])
 after=copy.deepcopy(before);after['nm_settings'].append(dict(nm_id=50,subject={'id':50},bids_kopecks={'search':28}))
 return IO(),dict(job_id=319,input_message_id=1005),dict(plan_id='remainder',items=[item],plan_sha256=digest([item])),dict(status='verified',items=[dict(id='a',status='verified',before=before,after=after)])
class Notices(unittest.TestCase):
 def test_partial_then_verified_once(self):
  io,a,p,e=fixture();blocked=copy.deepcopy(e);blocked['items'][0].update(status='blocked',reason='minimum context')
  deliver(io,a,p,blocked);deliver(io,a,p,e);deliver(io,a,p,e)
  self.assertEqual(len(io.sent),2);self.assertEqual(io.data[ns['PREFIX']+'remainder:verified']['status'],'sent')
  self.assertIn('0.28 CNY',io.sent[-1][1]['text'])
 def test_no_replay_on_transport_uncertainty(self):
  io,a,p,e=fixture();io.fail=True;deliver(io,a,p,e);deliver(io,a,p,e)
  self.assertEqual(len(io.sent),1)
 def test_missing_readback_never_success(self):
  io,a,p,e=fixture();e['items'][0].pop('after');deliver(io,a,p,e)
  self.assertNotIn('проверено WB',io.sent[0][1]['text'])
 def test_original_unknown_legacy_receipt_not_resent(self):
  io,a,p,e=fixture();io.data[ns['PREFIX']+'remainder']={'status':'sent','message_id':5};deliver(io,a,p,e);self.assertFalse(io.sent)
 def test_own_registered_completion_checks_authorization_and_receipts(self):
  import sys,types
  from unittest.mock import patch
  io,a,p,e=fixture()
  auth=dict(status='approved',owner_id=5122667182,telegram_allowed=True,chat_id=CHAT,bot_id=BOT,execution_key='root',plan_sha256=p['plan_sha256'],job_id=319,input_message_id=1005)
  io.data['auth']=auth;e['completion_notice']=dict(authorization_key='auth',plan=p,approval=a)
  with patch.dict(sys.modules,{'china_loss_control':types.SimpleNamespace(digest=digest)}):
   ns['deliver_registered'](io,'root',e);ns['deliver_registered'](io,'root',e)
   self.assertEqual(len(io.sent),1)
   io.data['auth']['owner_id']=1
   with self.assertRaises(ValueError):ns['deliver_registered'](io,'root',e)
if __name__=='__main__':unittest.main()


