import unittest,copy
from datetime import datetime,date,timezone
from types import SimpleNamespace
from china_shared_advertising import shared
from china_analytic_dialog import Analyst
from china_experience import ROOT,put_event
class ReplayRegressions(unittest.TestCase):
 def fixture(self,missing=False):
  n=dict(nmId=1,sum=5,sum_price=100,orders=1,clicks=10,views=100,atbs=2)
  n2=dict(nmId=1,sum=3,sum_price=0,orders=0,clicks=6,views=50,atbs=4)
  if missing:n2.pop('atbs')
  d=dict(date='2026-10-25T00:00:00Z',sum=8,sum_price=100,orders=1,clicks=16,views=150,atbs=6,apps=[dict(nms=[n]),dict(nms=[n2])])
  base=dict(status='complete',period_from='2026-10-19',period_to='2026-10-24',observed_at='2026-10-25T10:00:00+00:00',batches={'0':dict(campaigns=dict(adverts=[dict(id=42,status=9,settings={},nm_settings=[dict(nm_id=1)])]),stats=[])})
  current=dict(observed_at='2026-10-25T17:00:00+00:00',ad_batches=[dict(data=[dict(advertId=42,days=[d])])])
  cache={'china_agent:advertising_source:2026-10-25:v2':base,'china_agent:advertising_intraday:2026-10-25:v1':current}
  return SimpleNamespace(now=datetime(2026,10,25,17,tzinfo=timezone.utc),get=lambda k:copy.deepcopy(cache.get(k)))
 def test_baskets_sum_apps_once(self):
  r=shared(self.fixture(),date(2026,10,25),date(2026,10,25),[1]);m=r['products']['1']['42']['2026-10-25']
  self.assertEqual(m['basket_events'],6);self.assertEqual(m['spend_cny'],8);self.assertEqual(m['orders'],1)
  self.assertEqual(r['totals_by_day']['2026-10-25']['spend_cny'],8);self.assertEqual(r['wb_reads'],0)
 def test_missing_baskets_are_unknown(self):
  r=shared(self.fixture(True),date(2026,10,25),date(2026,10,25),[1])
  self.assertIsNone(r['products']['1']['42']['2026-10-25']['basket_events'])
 def test_missing_profit_is_not_zero(self):
  w=SimpleNamespace(now=datetime(2026,10,25,tzinfo=timezone.utc),get=lambda k:None)
  r=Analyst(w,{},[]).profit('2026-10-24','2026-10-25')
  self.assertFalse(r['available']);self.assertNotIn('expected_rub',r)
 def test_saved_forecast_preserves_uncertainty(self):
  value=dict(status='available_preliminary',all_expenses_confirmed=False,is_closed_net_profit=False,summary=[dict(expected_rub=100)])
  w=SimpleNamespace(now=datetime(2026,10,25,tzinfo=timezone.utc),get=lambda k:copy.deepcopy(value))
  r=Analyst(w,{},[]).profit('2026-10-24','2026-10-25')
  self.assertEqual(r['summary'][0]['expected_rub'],100);self.assertFalse(r['is_closed_net_profit']);self.assertFalse(r['all_expenses_confirmed']);self.assertEqual(r['wb_reads'],0)
 def test_profit_future_date_rejected(self):
  w=SimpleNamespace(now=datetime(2026,10,25,tzinfo=timezone.utc),get=lambda k:None)
  with self.assertRaises(ValueError):Analyst(w,{},[]).profit('2026-10-25','2026-10-26')
 def test_prefetched_event_does_not_read_or_overwrite(self):
  original=dict(event_id='known',record_type='verified_action',source_key='receipt',business_outcome='negative')
  w=SimpleNamespace(_experience_prefetched={ROOT+'known':original},get=lambda k:(_ for _ in ()).throw(AssertionError('Unnecessary per-event read')))
  result=put_event(w,dict(original,business_outcome='pending'));self.assertEqual(result['business_outcome'],'negative')
 def test_new_event_is_added_to_prefetched_view(self):
  saved=[];w=SimpleNamespace(_experience_prefetched={},get=lambda k:None,save=lambda k,v:saved.append((k,v)))
  event=dict(event_id='new',record_type='verified_action',source_key='receipt')
  first=put_event(w,event);second=put_event(w,event)
  self.assertEqual(first,second);self.assertEqual(sum(k==ROOT+'new' for k,v in saved),1)
if __name__=='__main__':unittest.main()
