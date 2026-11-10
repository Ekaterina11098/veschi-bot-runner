import ast,unittest
from pathlib import Path

class ClosedMidday(unittest.TestCase):
 def prepare(self,spend):
  source=Path(__file__).with_name('china_advertising_midday.py').read_text(encoding='utf-8')
  fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)and n.name=='prepare_midday')
  scope=dict(price_map=lambda x:{},history=lambda x:[],never_started_draft=lambda x:False,current_report_context=lambda *a:([],{}),daily_metrics=lambda d:dict(spend=d['sum'],amount=0,orders=0,clicks=0,views=1))
  exec(compile(ast.Module(body=[fn],type_ignores=[]),'midday','exec'),scope)
  def campaign(cid,status):return dict(id=cid,status=status,settings=dict(placements={},name='Test'),nm_settings=[])
  data=dict(catalogue={},observed_at='2026-11-10T12:00:00+00:00',batches=dict(one=dict(campaigns=dict(adverts=[campaign(1,9),campaign(2,7)]),stats=[dict(advertId=cid,days=[dict(date='2026-11-10',sum=amount,apps=[])])for cid,amount in [(1,0),(2,spend)]])))
  return scope['prepare_midday'](None,'2026-11-10',data)
 def test_closed_cpm_cost_is_kept(self):
  result=self.prepare(.05)
  self.assertEqual(2,len(result['campaigns']))
  self.assertEqual(.05,result['campaigns'][1]['today']['spend'])
 def test_closed_campaign_with_impressions_is_kept_at_zero_spend(self):
  self.assertEqual(2,len(self.prepare(0)['campaigns']))

if __name__=='__main__':unittest.main()