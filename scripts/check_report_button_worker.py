import sys,types,unittest,json,copy,hashlib
from urllib.parse import parse_qs
loss=types.ModuleType('china_loss_control');loss.PLAN='plan:';loss.APPROVAL='approval:';loss.CHAT=-1004342917488;loss.BOT=8780468043
loss.digest=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
loss.marker=lambda job:job['tool_trace'][0];sys.modules['china_loss_control']=loss
valid=types.ModuleType('china_daily_report_validity');valid.valid=lambda io,p:not p.get('invalidated_at');sys.modules[valid.__name__]=valid
import china_report_buttons as b
class IO:
 def __init__(self):self.cache={}
 def get(self,k):return copy.deepcopy(self.cache.get(k))
 def create(self,k,v):
  if k in self.cache:return False
  self.cache[k]=copy.deepcopy(v);return True
 def put(self,k,v):self.cache[k]=copy.deepcopy(v)
 def db(self,path,method='GET',body=None,prefer=None):
  q=parse_qs(path.split('?',1)[1]);k=q['cache_key'][0][3:]
  if json.loads(q['payload'][0][3:])!=self.cache[k]:return []
  self.cache[k]=copy.deepcopy(body['payload']);return [body]
class TestButtons(unittest.TestCase):
 def test_shared_gate(self):
  io=IO();b.claim(io,'p',['drr'],'button:a');b.claim(io,'p',['drr'],'button:a');b.claim(io,'p',['budgets'],'button:b')
  with self.assertRaises(ValueError):b.claim(io,'p',['drr','budgets'],'job:5')
  self.assertEqual(io.get(b.GATE+'p')['domains'],{'drr':'button:a','budgets':'button:b'})
 def test_filter_and_selection(self):
  io=IO();io.cache[b.ROOT+'policy']={'enabled':True}
  items=[dict(id='a',kind='ad_set_bid',article='A',campaign_id=1,old_minor=28,target_minor=30),dict(id='f',kind='topup_campaign',campaign_id=1,amount_cny=100)]
  p=dict(plan_id='p',plan_sha256=loss.digest(items),items=items,expires_at='2099-01-01T00:00:00Z',family='drr',report_message_ids=[10])
  io.cache['plan:p']=p
  keyboard=b.prepare(io,p,'budgets');token=keyboard['inline_keyboard'][0][0]['callback_data'].split(':')[1]
  self.assertEqual(io.get(b.ROOT+'plan:'+token)['items'][0]['id'],'f')
  ct=token+'-7';io.cache[b.ROOT+'confirmation:'+ct]=dict(status='confirmed',job_id=9,sender_id=7,chat_id=loss.CHAT,plan_id='p',plan_sha256=p['plan_sha256'],selected_ids=['f'],review_message_id=99,report_message_id=10)
  job=dict(id=9,sender_id=7,update_id=12,created_at='2026-11-11T08:00:00Z',tool_trace=[dict(bot_id=loss.BOT,message_id=10,reply_message_id=10,report_button_confirmation=ct)])
  b.handle(io,job);a=io.get('approval:9');child=io.get('plan:'+a['plan_id'])
  self.assertEqual(child['items'],[items[1]]);self.assertEqual(a['result_message_id'],99);self.assertTrue(b.validate(io,a,job))
  p['invalidated_at']='now';io.cache['plan:p']=p;self.assertFalse(b.validate(io,a,job))
if __name__=='__main__':unittest.main()

