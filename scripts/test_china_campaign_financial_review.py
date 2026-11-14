import copy,sys,types,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from china_campaign_financial_review import apply

class Review(unittest.TestCase):
 def fixture(self,status=9,orders=2,margin=5,spend=30):
  now=datetime.now(timezone.utc);day=(now+timedelta(hours=3)).date().isoformat();days=[((now+timedelta(hours=3))-timedelta(days=n)).date().isoformat()for n in(3,2,1)]
  state=dict(id=10,status=status,bid_type='manual',settings=dict(payment_type='cpc',placements=dict(search=True)),nm_settings=[dict(nm_id=20,bids_kopecks=dict(search=27))])
  row=dict(buyout=.7,sample_size=5,buyout_fallback=False,expected_margin_before_ads_cny=margin,own_cogs_rub=10,seller_price_cny=30,stock_free=10,published_stock=10,logistics_cny=2,fx_rub_per_cny=12,observed_at=now.isoformat(),stock_observed_at=now.isoformat(),price_observed_at=now.isoformat())
  raw=dict(advertId=10,days=[dict(date=d,sum=spend/3,clicks=40,orders=orders if d==days[-1]else 0,apps=[dict(nms=[dict(nmId=20,sum=spend/3,orders=orders if d==days[-1]else 0)])])for d in days])
  source=dict(observed_at=now.isoformat(),config=dict(minTopUp=10000),executions=[],economics=dict(rows={'20':row}),batches=dict(a=dict(campaigns=dict(adverts=[state]),stats=[raw])))
  bundle=dict(day=day,days=days,campaigns=[dict(id=10,name='test',balance=0,focus=[],attention=[],period={})])
  return bundle,source,{'10:20':27 if status==9 else 23}
 def run_case(self,b,s,m):
  module=types.SimpleNamespace(history=lambda records:[],http=lambda *args:(_ for _ in()).throw(AssertionError('Unexpected read')))
  with patch.dict(sys.modules,{'china_advertising_v2':module}):return apply(types.SimpleNamespace(get=lambda key:{}),b,s,m)['campaigns'][0]
 def test_negative_small_order_sample_is_pause_proposal(self):
  b,s,m=self.fixture();self.assertEqual(self.run_case(b,s,m)['financial_action']['kind'],'pause_campaign')
 def test_positive_small_sample_not_paused(self):
  b,s,m=self.fixture(margin=30);self.assertNotIn('financial_action',self.run_case(b,s,m))
 def test_missing_associated_economics_not_zero(self):
  b,s,m=self.fixture();s['batches']['a']['stats'][0]['days'][-1]['apps'][0]['nms'][0]['nmId']=99
  self.assertNotIn('financial_action',self.run_case(b,s,m))
 def test_planned_buyout_can_show_risk_but_not_fund_restart(self):
  b,s,m=self.fixture();e=s['economics']['rows']['20'];e.update(sample_size=0,buyout_fallback=True)
  self.assertEqual(self.run_case(b,s,m)['financial_action']['kind'],'pause_campaign')
  b,s,m=self.fixture(status=11,margin=60);s['economics']['rows']['20'].update(sample_size=0,buyout_fallback=True)
  self.assertNotIn('financial_action',self.run_case(b,s,m))
 def test_atomic_recovery_requires_stress_positive_and_all_stock(self):
  b,s,m=self.fixture(status=11,orders=5,margin=60);c=self.run_case(b,s,m);a=c['financial_action'];self.assertEqual((a['kind'],a['target_minor'],a['amount_cny']),('recover_campaign',23,100))
  s['economics']['rows']['20']['published_stock']=0;self.assertNotIn('financial_action',self.run_case(b,s,m))
 def test_current_day_ignored_and_input_unchanged(self):
  b,s,m=self.fixture();before=copy.deepcopy(s);s['batches']['a']['stats'][0]['days'].append(dict(date=b['day'],sum=10000,orders=0,clicks=10000))
  self.assertEqual(self.run_case(b,s,m)['financial_action']['risk_evidence']['spend_cny'],30)
  self.assertEqual(s['economics'],before['economics'])
if __name__=='__main__':unittest.main()
