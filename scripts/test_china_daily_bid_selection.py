import copy,unittest
from datetime import datetime,timedelta,timezone
from china_loss_control import CHAT,BOT,PLAN,digest
from china_daily_bid_selection import command,prepare,validate,BIND
class Store:
 def __init__(self):
  now=datetime.now(timezone.utc);items=[dict(id=str(i),kind='ad_set_bid',old_minor=28,target_minor=30,campaign_id=1,nm_id=i,placement='search')for i in range(1,8)]+[dict(id='excluded',kind='ad_exclude_sku',nm_id=99)]
  p=dict(plan_id='example',execution_kind='daily_ad_actions_v2',family='drr',chat_id=CHAT,items=items,plan_sha256=digest(items),created_at=(now-timedelta(minutes=2)).isoformat(),expires_at=(now+timedelta(hours=1)).isoformat(),report_message_ids=[10])
  self.values={PLAN+'example':p,BIND+'10':dict(plan_id='example',chat_id=CHAT,plan_sha256=p['plan_sha256'])}
  self.job=dict(id=1,update_id=2,sender_id=307200273,chat_id=CHAT,created_at=now.isoformat(),request_text='/codex Не исключай из рекламы. Повысь и понизь ставки',tool_trace=[dict(name='china_saved_question',bot_id=BOT,message_id=11,reply_message_id=10)])
 def get(self,k):return copy.deepcopy(self.values.get(k))
 def save(self,k,v,insert=False):
  if insert and k in self.values:return False
  self.values[k]=copy.deepcopy(v);return True
class Tests(unittest.TestCase):
 def test_subset_and_dedup(self):
  s=Store();a,p=prepare(s,s.job);self.assertEqual(7,len(p['items']));self.assertTrue(all(i['kind']=='ad_set_bid'for i in p['items']));self.assertEqual((a,p),prepare(s,s.job));self.assertTrue(validate(s,a,s.job))
 def test_parent_revoked_after_approval(self):
  s=Store();a,p=prepare(s,s.job);s.values[PLAN+'example']['invalidated_at']='now'
  with self.assertRaises(ValueError):validate(s,a,s.job)
 def test_hash_expiry_forward_and_wrong_reply_rejected(self):
  for change in ('hash','expired','forward','reply'):
   s=Store()
   if change=='hash':s.values[PLAN+'example']['plan_sha256']='bad'
   if change=='expired':s.values[PLAN+'example']['expires_at']='2000-01-01T00:00:00+00:00'
   if change=='forward':s.job['tool_trace'][0]['forwarded']=True
   if change=='reply':s.job['tool_trace'][0]['reply_message_id']=999
   with self.assertRaises(ValueError):prepare(s,s.job)
 def test_negatives_and_embedded_quotes_are_not_approval(self):
  for text in ('Не повышай ставки','Повысь и понизь ставки?','Процитируй: повысь и понизь ставки','Повысь и понизь ставки и пополни бюджет'):
   self.assertFalse(command(text))
if __name__=='__main__':unittest.main()
