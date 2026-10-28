import copy,unittest
from datetime import timedelta
from china_price_minimum import *
from test_china_price_apply import Fake
from china_price_apply import process
class MinimumTests(unittest.TestCase):
 def result(self):
  f=Fake();e=process(f,f.key,polls=1,pause=lambda _:None);return f,e
 def test_floor_exact_decimals_and_invalid(self):
  self.assertEqual(floor_price('273.35'),273);self.assertEqual(floor_price('273'),273)
  for x in [None,0,-1,'NaN','Infinity',True,'1,5']:
   with self.assertRaises(ValueError):floor_price(x)
 def test_verified_price_only_creates_explicit_pending_minimum(self):
  f,e=self.result();self.assertEqual(f.writes,1);self.assertEqual(e['minimum_prices']['rows'][0]['minimum_cny'],110)
  self.assertFalse(e['minimum_prices']['minimums_wb_verified']);self.assertIn('ещё не подтверждены',note(e))
  process(f,f.key,polls=1,pause=lambda _:None);self.assertEqual(f.writes,1)
 def test_uncertain_price_has_no_minimum_success_or_second_write(self):
  f=Fake();f.fail=True;e=process(f,f.key,polls=1,pause=lambda _:None);self.assertEqual(e['status'],'uncertain')
  self.assertFalse(e.get('minimum_prices'));self.assertEqual(f.writes,1)
 def test_block_changes_expired_missing_or_changed_price_never_verify(self):
  f,e=self.result();rs=e['minimum_prices']['rows'];n=datetime.now(timezone.utc)
  row=dict(nm_id='1',article='A',currency='CNY',seller_cny='110',minimum_cny=110,minimum_expires_at=(n+timedelta(days=30)).isoformat(),block=dict(mode='Бессрочно'))
  before=dict(source='WB_seller_cabinet_export',observed_at=n.isoformat(),rows={'1':copy.deepcopy(row)});after=copy.deepcopy(before)
  self.assertEqual(verify(rs,before,after,n)['status'],'verified')
  for change in [dict(block=dict(mode='Нет')),dict(minimum_cny=109),dict(minimum_cny=110.0),dict(seller_cny='111'),dict(minimum_expires_at=n.isoformat()),dict(currency='RUB'),dict(article='other')]:
   bad=copy.deepcopy(after);bad['rows']['1'].update(change);self.assertEqual(verify(rs,before,bad,n)['status'],'not_verified')
  bad=copy.deepcopy(before);bad['rows']['1'].pop('block');self.assertEqual(verify(rs,bad,after,n)['status'],'not_verified')
 def test_upload_ack_or_owner_done_is_not_wb_readback(self):
  f,e=self.result();rs=e['minimum_prices']['rows'];n=datetime.now(timezone.utc)
  for data in [dict(status='done'),dict(upload_id=1),dict(source='owner_statement',observed_at=n.isoformat(),rows={})]:
   self.assertEqual(verify(rs,data,data,n)['status'],'not_verified')
 def test_missing_readback_cannot_cancel_price_success_or_repeat_post(self):
  f,e=self.result();bad=copy.deepcopy(e);bad['items'][0]['readback'].pop('editableSizePrice')
  attach(bad);self.assertEqual(bad['status'],'done');self.assertEqual(bad['minimum_prices']['status'],'required_not_verified')
  self.assertFalse(bad['minimum_prices']['minimums_wb_verified'])
 def test_stale_export_not_verified(self):
  f,e=self.result();n=datetime.now(timezone.utc);old=dict(source='WB_seller_cabinet_export',observed_at=(n-timedelta(hours=1)).isoformat(),rows={})
  self.assertEqual(verify(e['minimum_prices']['rows'],old,old,n)['status'],'not_verified')
if __name__=='__main__':unittest.main()
