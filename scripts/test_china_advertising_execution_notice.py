import copy,unittest
from unittest.mock import patch
from china_execution_notice import deliver_result,PREFIX
from china_daily_ad_actions import execute,EXEC
from china_loss_control import digest
CHAT=-1004342917488;BOT=8780468043
class IO:
 def __init__(self):self.data={};self.sent=[];self.fail=False
 def get(self,k):return copy.deepcopy(self.data.get(k))
 def create(self,k,v):
  if k in self.data:return False
  self.data[k]=copy.deepcopy(v);return True
 def put(self,k,v):self.data[k]=copy.deepcopy(v)
 def validate_owner(self,a):pass
 def tg(self,method,body):
  self.sent.append((method,body))
  if self.fail:raise TimeoutError()
  return dict(message_id=999,chat=dict(id=CHAT),**{'from':dict(id=BOT)})
def fixture():
 item=dict(id='41055480:98',kind='ad_exclude_sku',campaign_id=41055480,nm_id=98,article='98-Emma',old_minor=28)
 before=dict(id=41055480,status=9,settings=dict(name='Сумки 2'),nm_settings=[dict(nm_id=98,bids_kopecks=dict(search=0,recommendations=28)),dict(nm_id=585,bids_kopecks=dict(search=0,recommendations=38))])
 after=copy.deepcopy(before);after['nm_settings']=after['nm_settings'][1:]
 p=dict(plan_id='p',items=[item],plan_sha256=digest([item]),execution_kind='daily_ad_actions_v2')
 a=dict(job_id=150,input_message_id=385,plan_sha256=p['plan_sha256'])
 e=dict(status='done',items=[dict(id=item['id'],status='verified',before=before,after=after)],wb_writes=1)
 return IO(),a,p,e
class Notices(unittest.TestCase):
 def test_verified_once_and_reply(self):
  io,a,p,e=fixture();deliver_result(io,a,p,e);deliver_result(io,a,p,e)
  self.assertEqual(len(io.sent),1);self.assertEqual(io.sent[0][1]['reply_parameters']['message_id'],385);self.assertIn('проверено WB',io.sent[0][1]['text'])
 def test_direct_execute_also_delivers(self):
  io,a,p,e=fixture();io.data[EXEC+'p']=e
  execute(io,a,p);self.assertEqual(len(io.sent),1)
 def test_unexpected_other_bid_never_claims_success(self):
  io,a,p,e=fixture();e['items'][0]['after']['nm_settings'][0]['bids_kopecks']['recommendations']=30
  deliver_result(io,a,p,e);self.assertNotIn('проверено WB',io.sent[0][1]['text']);self.assertIn('не подтверждён',io.sent[0][1]['text'])
 def test_readback_pending_then_verified(self):
  io,a,p,e=fixture();pending=copy.deepcopy(e);pending['items'][0]['status']='uncertain'
  deliver_result(io,a,p,pending);deliver_result(io,a,p,pending);deliver_result(io,a,p,e)
  self.assertEqual(len(io.sent),2);self.assertEqual(io.data[PREFIX+'p']['phase'],'verified')
 def test_telegram_timeout_no_blind_retry(self):
  io,a,p,e=fixture();io.fail=True;deliver_result(io,a,p,e);deliver_result(io,a,p,e)
  self.assertEqual(len(io.sent),1);self.assertEqual(io.data[PREFIX+'p']['status'],'uncertain')
 def test_existing_manual_confirmation_not_resent(self):
  io,a,p,e=fixture();io.data[PREFIX+'p']=dict(status='sent',message_id=388);deliver_result(io,a,p,e);self.assertEqual(io.sent,[])
 def test_verified_flag_without_readbacks_is_not_success(self):
  io,a,p,e=fixture();del e['items'][0]['after'];deliver_result(io,a,p,e);self.assertNotIn('проверено WB',io.sent[0][1]['text'])
 def test_blocked_is_explicit(self):
  io,a,p,e=fixture();e['items'][0].update(status='blocked',reason='Bid changed');deliver_result(io,a,p,e);self.assertIn('не выполнено: Bid changed',io.sent[0][1]['text'])
if __name__=='__main__':unittest.main()

