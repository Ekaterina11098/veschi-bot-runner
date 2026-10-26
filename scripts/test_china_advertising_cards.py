import unittest,copy
from china_advertising_cards import enhance
from china_advertising_v2_png import render
from test_china_advertising_v2 import campaign,row
def fixture():
 c=campaign();c['nm_settings']=c['nm_settings'][1:]
 old=campaign();old['nm_settings']+=[dict(nm_id=3,bids_kopecks=dict(recommendations=28,search=0))]
 excluded=copy.deepcopy(old);excluded['nm_settings']=excluded['nm_settings'][1:]
 labels=[dict(nmID=i,vendorCode='sku'+str(i),price=100) for i in [1,2,3]]
 n=dict(nmId=2,sum=1,sum_price=0,orders=0,views=10,clicks=3)
 day=dict(date='2026-10-25',sum=20,sum_price=100,orders=1,views=100,clicks=20,apps=[dict(nms=[n])])
 s=dict(catalogue=dict(rows=labels),executions=[dict(payload=dict(status='verified',before=old,after=excluded,verified_at='2026-10-23T10:00:00Z'))],batches={'0':dict(stats=[dict(advertId=12,days=[day])],campaigns=dict(adverts=[c]))})
 card=dict(id=12,name='Test',zone='рекомендации',balance=50,status=9,drr=20,focus=[],last=row(20,100),period=row(20,100),missing_stats=False,budget_action=None)
 b=dict(day='2026-10-26',days=['2026-10-23','2026-10-24','2026-10-25'],source_observed_at='26.10.2026 07:30 МСК',campaigns=[card])
 return b,s
class CardFactsTests(unittest.TestCase):
 def test_old_verified_exclusion_in_three_day_window_is_visible(self):
  b,s=fixture();v=enhance(b,s)['campaigns'][0]
  self.assertEqual([x['nm'] for x in v['confirmed_exclusions']],[1]);self.assertIn('sku1',v['notes'][0])
 def test_uncertain_is_not_called_excluded(self):
  b,s=fixture();s['executions'][0]['payload']['status']='uncertain'
  self.assertEqual(enhance(b,s)['campaigns'][0]['confirmed_exclusions'],[])
 def test_readded_member_not_called_excluded(self):
  b,s=fixture();s['batches']['0']['campaigns']['adverts'][0]['nm_settings'].append(dict(nm_id=1))
  self.assertEqual(enhance(b,s)['campaigns'][0]['confirmed_exclusions'],[])
 def test_aggregate_and_remaining_member_spend_not_conflated(self):
  b,s=fixture();v=enhance(b,s)['campaigns'][0]
  self.assertEqual(v['period']['spend'],20);self.assertEqual(v['current_period']['spend'],1)
  self.assertIn('1,00',v['notes'][1]);self.assertIn('Максимум',v['notes'][2])
 def test_waiting_rows_not_in_individual_attention(self):
  b,s=fixture();b['campaigns'][0]['focus']=[dict(nm=2,article='sku2',action=None,reason='Малая выборка',decision='Сохранить ставку')]
  self.assertEqual(enhance(b,s)['campaigns'][0]['attention'],[])
 def test_no_pause_bound_to_report(self):
  b,s=fixture();b['campaigns'][0]['budget_action']=dict(kind='pause_campaign')
  self.assertIsNone(enhance(b,s)['campaigns'][0]['budget_action'])
 def test_render_keeps_families_and_exact_actions(self):
  b,s=fixture();a=dict(kind='ad_exclude_sku',id='12:2')
  b['campaigns'][0]['focus']=[dict(nm=2,article='sku2',period=row(10,0),action=a,decision='Исключить',reason='Расход без заказов')]
  pages=render(enhance(b,s));self.assertEqual({x['family'] for x in pages},{'drr','budgets'})
  self.assertEqual([a for p in pages for a in p['actions']],[a])
  self.assertTrue(all(p['bytes'].startswith(b'\x89PNG') for p in pages))
 def test_yesterday_is_separate_from_partial_today(self):
  b,s=fixture()
  s['intraday']=dict(observed_at='2026-10-26T06:10:00Z',ad_batches=[dict(data=[dict(advertId=12,days=[dict(date='2026-10-26',sum=2,sum_price=0,orders=0,views=10,clicks=3)])])])
  c=enhance(b,s)['campaigns'][0]
  self.assertEqual(c['today']['spend'],2);self.assertEqual(c['yesterday']['spend'],20)
  self.assertEqual(b['total_yesterday_spend'],20)
 def test_missing_today_never_replaced_by_yesterday(self):
  b,s=fixture();self.assertIsNone(enhance(b,s)['campaigns'][0]['today'])
 def test_missing_stats_not_zero(self):
  b,s=fixture();b['campaigns'][0]['missing_stats']=True
  self.assertIsNone(enhance(b,s)['campaigns'][0]['current_period'])
if __name__=='__main__':unittest.main()
