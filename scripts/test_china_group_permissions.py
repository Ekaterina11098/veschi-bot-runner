import unittest
from types import SimpleNamespace
from china_group_permissions import allowed,KEY
from china_loss_control import CHAT,BOT,OWNER
class GroupPermissions(unittest.TestCase):
 def fixture(self,status='member',is_bot=False,member_id=42,is_member=True):
  policy=dict(enabled=True,policy='all_current_human_group_members',chat_id=CHAT,bot_id=BOT)
  w=SimpleNamespace(get=lambda k:policy if k==KEY else None,config=lambda:dict(chat_id=CHAT,bot_id=BOT,owner_user_id=OWNER),member_check=lambda actor:dict(status=status,is_member=is_member,user=dict(id=member_id,is_bot=is_bot)))
  j=dict(agent_id='china',sender_id=42,chat_id=CHAT,tool_trace=[dict(name='china_saved_question',bot_id=BOT)])
  return w,j
 def test_every_current_human_role(self):
  for status in ('member','administrator','creator','restricted'):
   w,j=self.fixture(status=status);self.assertTrue(allowed(w,j))
 def test_left_kicked_bot_or_wrong_identity_rejected(self):
  for kwargs in (dict(status='left'),dict(status='kicked'),dict(is_bot=True),dict(member_id=99),dict(status='restricted',is_member=False)):
   w,j=self.fixture(**kwargs);self.assertFalse(allowed(w,j))
 def test_outside_group_or_forward_rejected(self):
  w,j=self.fixture();j['chat_id']=-1;self.assertFalse(allowed(w,j))
  w,j=self.fixture();j['tool_trace'][0]['forwarded']=True;self.assertFalse(allowed(w,j))
 def test_live_lookup_failure_rejected(self):
  w,j=self.fixture()
  def fail(actor):raise RuntimeError('offline')
  w.member_check=fail;self.assertFalse(allowed(w,j))
 def test_legacy_registration_preserved_until_enable(self):
  w=SimpleNamespace(get=lambda k:None,config=lambda:dict(chat_id=-1,bot_id=9,owner_user_id=5))
  self.assertTrue(allowed(w,dict(chat_id=-1,sender_id=5)))
  self.assertFalse(allowed(w,dict(chat_id=-1,sender_id=6)))
if __name__=='__main__':unittest.main()
