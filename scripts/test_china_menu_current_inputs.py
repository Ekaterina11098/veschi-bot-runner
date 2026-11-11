import unittest,types,sys,copy,contextlib,hashlib
from unittest.mock import patch
import china_menu_analytics as menu
class CompleteCandidate(unittest.TestCase):
 def test_recalculation_then_four_direction_plan_freezes_and_keeps_labels(self):
  data={};calls=[]
  class W:
   def get(self,k):return data.get(k)
   def save(self,k,v,insert=False):data[k]=copy.deepcopy(v);return True
  class IO:
   def get(self,k):return None
   def put(self,k,v):pass
   def create(self,k,v):return True
  action=dict(id='1:7',kind='ad_set_bid',direction='reduce',campaign_id=1,nm_id=7,article='item',placement='recommendations',old_minor=30,target_minor=28)
  def prepare(io,day):
   calls.append('prepare');cost=21 if any(k.startswith('china_agent:menu_current_inputs')for k in data)else 20
   row=dict(nm=7,article='item',action=action,economics=dict(seller_price_cny=100,own_cogs_rub=cost))
   return dict(days=['2026-11-08','2026-11-09','2026-11-10'],campaigns=[dict(id=1,focus=[row],attention=[copy.deepcopy(row)])],recommendation_directions={k:dict(status='available',rows=[dict(ready=True,action=action)]if k=='reduce'else[],count=1 if k=='reduce'else 0)for k in menu.LABELS})
  state=dict(id=1,currency='CNY',status=9,nm_settings=[dict(nm_id=7,bids_kopecks=dict(recommendations=30))])
  modules={
   'china_analytic_dialog':types.SimpleNamespace(reading=contextlib.nullcontext),
   'china_loss_execute':types.SimpleNamespace(IO=IO),
   'china_advertising_v2':types.SimpleNamespace(prepare=prepare,http=lambda *a,**k:dict(adverts=[state])),
   'china_advertising_v2_png':types.SimpleNamespace(render=lambda b:[dict(family='drr',bytes=b'png')]),
   'china_loss_control':types.SimpleNamespace(PLAN='plan:',digest=lambda x:hashlib.sha256(repr(x).encode()).hexdigest()),
   'china_morning_rules_review':types.SimpleNamespace(enabled=lambda io:True),
   'china_advertising_growth':types.SimpleNamespace(validate_raise=lambda *a:None),
   'china_advertising_full_growth':types.SimpleNamespace(validate_addition=lambda *a:None),
   'china_morning_readiness':types.SimpleNamespace(current_prices=lambda *a:dict(rows=[dict(nm_id=7,article='item',seller_price=100)]),published_stock=lambda *a:dict(amounts={'7':5})),
   'china_moysklad_read':types.SimpleNamespace(read_stock=lambda *a:dict(coverage_complete=True,rows=[dict(article='item',price=2100,stock=5,reserve=0)])),
   'china_table_png':types.SimpleNamespace(KEY='png:',PREFIX='PHOTO:')}
  with patch.dict(sys.modules,modules):answer=menu.candidate(W(),dict(id=500,chat_id=-1004342917488,sender_id=5122667182),menu.CANDIDATES+'Все четыре направления:')
  self.assertEqual(calls,['prepare','prepare'])
  self.assertIn('Добавление товаров, Повышение ставок, Снижение ставок, Исключение из РК',answer)
  self.assertIn('Готовых действий: 1',answer)
  self.assertEqual(data['plan:dialog-menu-500']['items'],[action])
  self.assertEqual(data['png:500']['status'],'frozen')
if __name__=='__main__':unittest.main()

