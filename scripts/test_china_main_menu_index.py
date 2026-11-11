import unittest
from china_main_menu_index import bind,ROOT
class IO:
 def __init__(self):self.c={}
 def get(self,k):return self.c.get(k)
 def create(self,k,v):
  if k in self.c:return False
  self.c[k]=v;return True
 def put(self,k,v):self.c[k]=v
class IndexTest(unittest.TestCase):
 def test_pages_keep_own_plans_in_current_generation(self):
  io=IO()
  for i in (1,2):
   p=dict(plan_id='p'+str(i),plan_sha256='h'+str(i),report_generation='g')
   io.c['china_agent:daily_ad_current_report:v1:drr']=dict(plan_id=p['plan_id'])
   r=dict(message_id=i,date=1794380000,chat=dict(id=-1004342917488),**{'from':dict(id=8780468043)})
   bind(io,dict(family='drr',kind='drr:'+str(i)),p,r)
  self.assertEqual([x['plan_id']for x in io.c[ROOT+'drr']['pages']],['p1','p2'])
  self.assertEqual(io.c[ROOT+'drr']['message_ids'],[1,2])
 def test_replaced_generation_resets_without_old_pages(self):
  io=IO()
  for i in (1,2):
   p=dict(plan_id='p'+str(i),plan_sha256='h',report_generation='g'+str(i))
   io.c['china_agent:daily_ad_current_report:v1:drr']=dict(plan_id=p['plan_id'])
   bind(io,dict(family='drr'),p,dict(message_id=i,date=1794380000,chat=dict(id=-1004342917488),**{'from':dict(id=8780468043)}))
  self.assertEqual(io.c[ROOT+'drr']['message_ids'],[2])
 def test_wrong_chat_rejected(self):
  with self.assertRaises(ValueError):bind(IO(),dict(family='budgets'),{},dict(message_id=1,chat=dict(id=-1)))
if __name__=='__main__':unittest.main()
