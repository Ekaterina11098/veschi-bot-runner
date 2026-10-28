import unittest,copy
from china_advertising_midday import render_midday,recommendations
from china_advertising_delivery import deliver
from china_daily_ad_actions import plan
class IO:
 def __init__(self):self.d={}
 def get(self,k):return self.d.get(k)
 def create(self,k,v):
  if k in self.d:return False
  self.d[k]=copy.deepcopy(v);return True
 def put(self,k,v):self.d[k]=copy.deepcopy(v)
class MiddayTests(unittest.TestCase):
 def test_current_expense_and_no_orders(self):
  c=dict(draft=False,today=dict(spend=6.64,amount=0,orders=0,clicks=24,views=100),attention=[])
  self.assertEqual(['Нет'],recommendations(c))
 def test_exact_page_actions_and_green_png(self):
  a=dict(kind='ad_exclude_sku',campaign_id=1,nm_id=2)
  c=dict(id=1,name='Test',draft=False,today=dict(spend=10,amount=0,orders=0,clicks=40,views=100),attention=[dict(article='sku',decision='Исключить',action=a,spend=10,clicks=40)])
  f=render_midday(dict(day='2026-10-26',observed_at='2026-10-26T12:00:00Z',campaigns=[c]))
  self.assertEqual([a for p in f for a in p['actions']],[a])
  self.assertTrue(f[0]['bytes'].startswith(b'\x89PNG'))
 def test_separate_plan_identity(self):
  io=IO();f=dict(actions=[],family='drr')
  morning=plan(io,'2026-10-26',f,0);midday=plan(io,'2026-10-26',f,0,slot='midday')
  self.assertNotEqual(morning['plan_id'],midday['plan_id'])
 def test_delivery_dedup_and_no_morning_collision(self):
  io=IO();calls=[];files=[dict(kind='drr:001',bytes=b'image')]
  def send(f):calls.append(f);return dict(chat=dict(id=-1004342917488),message_id=1)
  k='china_agent:advertising_midday_delivery:2026-10-26:v1'
  for _ in range(2):deliver(io,'2026-10-26',files,send,delivery_key=k,expected_families={'drr'})
  self.assertEqual(len(calls),1);self.assertNotIn('china_agent:advertising_delivery:2026-10-26:v1',io.d)
 def test_uncertain_never_resent(self):
  io=IO();k='midday';io.d[k]=dict(status='uncertain',parts=[dict(kind='drr:001',status='uncertain',sha256=__import__('hashlib').sha256(b'image').hexdigest())])
  with self.assertRaises(RuntimeError):deliver(io,'2026-10-26',[dict(kind='drr:001',bytes=b'image')],lambda f:self.fail(),delivery_key=k,expected_families={'drr'})
if __name__=='__main__':unittest.main()
