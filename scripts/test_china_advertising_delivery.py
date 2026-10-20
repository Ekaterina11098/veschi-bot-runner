import copy,unittest
from china_advertising_delivery import deliver,CHAT
class Fake:
 def __init__(self):self.data={}
 def get(self,k):return copy.deepcopy(self.data.get(k))
 def create(self,k,p):
  if k in self.data:return False
  self.put(k,p);return True
 def put(self,k,p):self.data[k]=copy.deepcopy(p)
class DeliveryTests(unittest.TestCase):
 def setUp(self):
  self.io=Fake();self.files=[dict(kind='drr',bytes=b'first'),dict(kind='budgets',bytes=b'second')];self.calls=[]
 def send(self,f):
  self.calls.append(f['kind']);return dict(chat=dict(id=CHAT),message_id=len(self.calls)+80)
 def test_two_parts_and_second_pass_no_duplicates(self):
  a=deliver(self.io,'2026-10-20',self.files,self.send)
  b=deliver(self.io,'2026-10-20',self.files,self.send)
  self.assertEqual(a,b);self.assertEqual(self.calls,['drr','budgets'])
 def test_uncertain_second_never_repeats_first_or_second(self):
  def bad(f):
   if f['kind']=='budgets':raise TimeoutError()
   return self.send(f)
  with self.assertRaises(RuntimeError):deliver(self.io,'2026-10-20',self.files,bad)
  with self.assertRaises(RuntimeError):deliver(self.io,'2026-10-20',self.files,self.send)
  self.assertEqual(self.calls,['drr'])
 def test_crash_before_receipt_blocks_retry(self):
  def crash(f):raise KeyboardInterrupt()
  with self.assertRaises(KeyboardInterrupt):deliver(self.io,'2026-10-20',self.files,crash)
  with self.assertRaises(RuntimeError):deliver(self.io,'2026-10-20',self.files,self.send)
  self.assertEqual(self.calls,[])
 def test_changed_frozen_part_blocked(self):
  def crash(f):raise KeyboardInterrupt()
  with self.assertRaises(KeyboardInterrupt):deliver(self.io,'2026-10-20',self.files,crash)
  self.files[0]['bytes']=b'changed'
  with self.assertRaises(ValueError):deliver(self.io,'2026-10-20',self.files,self.send)
 def test_wrong_chat_uncertain(self):
  with self.assertRaises(RuntimeError):deliver(self.io,'2026-10-20',self.files,lambda f:dict(chat=dict(id=1),message_id=1))
  self.assertEqual(self.io.get('china_agent:advertising_delivery:2026-10-20:v1')['status'],'uncertain')
 def test_distinct_day_distinct_identity(self):
  deliver(self.io,'2026-10-20',self.files,self.send);deliver(self.io,'2026-10-21',self.files,self.send)
  self.assertEqual(len(self.calls),4)
if __name__=='__main__':unittest.main()
