import copy,types,unittest
from china_execution_notice import deliver_result,CHAT,BOT
class Notice(unittest.TestCase):
 def test_new_verified_subset_updates_same_card_once(self):
  cache={};calls=[]
  def create(k,v):
   if k in cache:return False
   cache[k]=copy.deepcopy(v);return True
  io=types.SimpleNamespace(get=lambda k:copy.deepcopy(cache.get(k)),create=create,put=lambda k,v:cache.update({k:copy.deepcopy(v)}),tg=lambda method,body:(calls.append((method,body))or dict(chat=dict(id=CHAT),from_=None,message_id=1040,**{'from':dict(id=BOT)})))
  items=[dict(id=str(cid),kind='topup_campaign',campaign_id=cid,amount_cny=100,target_balance=100)for cid in(1,2,3)]
  def verified(cid):return dict(id=str(cid),status='verified',before=dict(id=cid,status=9,settings={},nm_settings=[]),after=dict(id=cid,status=9,settings={},nm_settings=[]),before_budget=0,after_budget=100)
  e=dict(items=[verified(1),dict(id='2',status='blocked',reason='old'),dict(id='3',status='blocked',reason='minimum changed')]);p=dict(plan_id='p',plan_sha256='sha',items=items);a=dict(job_id=326,input_message_id=1037,result_message_id=1040)
  self.assertEqual(deliver_result(io,a,p,e)['status'],'sent')
  e['items'][1]=verified(2);self.assertEqual(deliver_result(io,a,p,e)['status'],'sent')
  self.assertIsNone(deliver_result(io,a,p,e));self.assertEqual(len(calls),2)
  self.assertTrue(all(m=='editMessageText'and b['message_id']==1040 for m,b in calls))
if __name__=='__main__':unittest.main()
