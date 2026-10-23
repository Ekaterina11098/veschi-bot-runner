import copy,unittest,sys,types
try:import requests
except ImportError:sys.modules['requests']=types.ModuleType('requests')
from unittest.mock import patch
from datetime import timedelta
import launch_confirmed_three as m
from test_china_new_ads import Transport as Original
class T(Original):
 def request(self,path,method='GET',body=None):
  if path=='/adv/v1/promotion/count':return dict(adverts=[])
  return super().request(path,method,body)
class I:
 def __init__(self):
  items=[]
  for i,(g,n) in enumerate([('orders_bags',2),('orders_umbrellas',3),('demand_umbrellas',3)]):
   items.append(dict(group=g,name=g,skus=[dict(nm_id=10*i+j+1,article=str(10*i+j+1),bid_minor=28 if i==0 else 23) for j in range(n)],budget_cny=100,daily_limit_minor=10000,auto_topup=False,carry_over_enabled=False,payment_type='cpc',bid_type='manual',placements=['recommendations']))
  p=dict(items=items,plan_sha256=m.digest(items),expires_at=(m.now()+timedelta(hours=1)).isoformat(),price_changes=False)
  self.mem={'china_agent:loss_plan:v1:'+m.PID:p,'china_agent:codex_approval:v1:'+m.PID:dict(source='explicit_human_codex_message',status='approved',quote='Да, запускай 3 РК по 100 юаней, всего 300. Проверь, чтобы всё прошло правильно.',plan_sha256=p['plan_sha256'])}
 def get(self,k):return copy.deepcopy(self.mem.get(k))
 def put(self,k,v):self.mem[k]=copy.deepcopy(v)
 def create(self,k,v):
  if k in self.mem:return False
  self.put(k,v);return True
 def validate_owner(self,a):pass
class Tests(unittest.TestCase):
 def test_all_three_checked_before_any_funding_and_idempotent(self):
  i=I();t=T()
  with patch.object(m,'IO',return_value=i),patch.object(m,'Transport',return_value=t):
   m.run();self.assertEqual(i.get(m.KEY)['status'],'done');m.run()
  self.assertEqual(len(t.c),3);self.assertEqual(sum(t.b.values()),300)
  first=next(j for j,r in enumerate(t.writes) if '/deposit' in r[0]);self.assertEqual(sum(r[0].endswith('daily-limits') for r in t.writes[:first]),3)
  first=next(j for j,r in enumerate(t.writes) if '/start' in r[0]);self.assertEqual(sum('/deposit' in r[0] for r in t.writes[:first]),3)
  self.assertEqual(len(t.writes),15)
 def test_lost_deposit_receipt_never_repeated(self):
  i=I();t=T();t.fail='deposit'
  with patch.object(m,'IO',return_value=i),patch.object(m,'Transport',return_value=t):m.run();m.run()
  self.assertEqual(i.get(m.KEY)['status'],'uncertain');self.assertEqual(sum(t.b.values()),100);self.assertFalse(any('/start' in r[0] for r in t.writes))
if __name__=='__main__':unittest.main()

