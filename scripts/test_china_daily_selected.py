import unittest,copy
from datetime import datetime,timezone,timedelta
from china_daily_selected import selected_command,source,prepare,validate
from china_loss_control import PLAN,digest
class IO:
 def __init__(self):self.data={}
 def get(self,k):return copy.deepcopy(self.data.get(k))
 def create(self,k,v):
  if k in self.data:return False
  self.data[k]=copy.deepcopy(v);return True
class Selected(unittest.TestCase):
 def fixture(self):
  now=datetime.now(timezone.utc);created=(now-timedelta(minutes=1)).isoformat();day=now.astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date().isoformat();io=IO()
  items=[dict(id=str(i),article=a,campaign_id=cid,nm_id=nm,kind='ad_exclude_sku') for i,(a,cid,nm) in enumerate([('673-Noel',1,1),('585-Regina',2,2),('98-EmmaBag-ginger',41055480,1473242754),('650-Kleo',3,4)])]
  p=dict(plan_id='p',items=items,plan_sha256=digest(items),created_at=created,expires_at=(now+timedelta(hours=2)).isoformat(),execution_kind='daily_ad_actions_v2')
  text='\n'.join(str(i)+'. '+x['article']+', РК '+str(x['campaign_id']) for i,x in enumerate(items,1))
  io.data[PLAN+'p']=p;io.data['china_agent:advertising_artifacts:'+day+':v2']=dict(files=[dict(plan_id='p',plan_sha256=p['plan_sha256'])]);io.data['china_agent:conversion_watch_delivery:v1:question:149:0']=dict(status='sent',chat_id=-1004342917488,message_id=384,text=text)
  j=dict(id=150,request_text='Выполни только 3 по списку предложение. Сумка 98',sender_id=307200273,chat_id=-1004342917488,update_id=3,created_at=now.isoformat(),tool_trace=[dict(name='china_saved_question',parent_job_id=149,bot_id=8780468043,message_id=385,reply_message_id=384,reply_text=text)])
  return io,j
 def test_only_one(self):
  io,j=self.fixture();a,p=prepare(io,j);self.assertEqual([x['nm_id'] for x in p['items']],[1473242754]);self.assertTrue(validate(io,a,j))
 def test_article_conflict(self):
  io,j=self.fixture();j['request_text']=j['request_text'].replace('98','650')
  with self.assertRaises(ValueError):source(io,j)
 def test_revoked(self):
  io,j=self.fixture();io.data[PLAN+'p']['invalidated_at']='now'
  with self.assertRaises(ValueError):source(io,j)
 def test_forged_quote(self):
  io,j=self.fixture();j['tool_trace'][0]['reply_text']='not original'
  with self.assertRaises(ValueError):source(io,j)
 def test_source_hash_changed(self):
  io,j=self.fixture();io.data[PLAN+'p']['items'].reverse()
  with self.assertRaises(ValueError):source(io,j)
 def test_30percent_not_selection(self):self.assertIsNone(selected_command('Выполни 30% самых дорогих'))
if __name__=='__main__':unittest.main()

