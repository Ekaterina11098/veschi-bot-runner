import importlib.util
import sys
import types
import unittest
import copy
from datetime import datetime,timedelta,timezone
from unittest.mock import patch

helper = types.ModuleType('china_cloud_cost_control')
helper.Cache = object
class FakeWB:
    def req(self, *args, **kwargs):
        return {'safe_read': True}
helper.WB = FakeWB
helper.validate_identity = lambda *a: None
helper.stamp = lambda: '2026-10-31T10:00:00+00:00'
spec = importlib.util.spec_from_file_location('collector', __file__.replace('test_china_', 'china_'))
m = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'china_cloud_cost_control': helper,
                             'requests': types.ModuleType('requests')}):
    spec.loader.exec_module(m)

class CollectorTest(unittest.TestCase):
    def cache(self):
        class C:
            def __init__(self):self.rows={};self.version=0;self.race=False
            def row(self,key):return copy.deepcopy(self.rows.get(key))
            def get(self,key):return copy.deepcopy((self.rows.get(key) or {}).get('payload'))
            def put(self,key,p):self.version+=1;self.rows[key]=dict(payload=copy.deepcopy(p),updated_at=str(self.version))
            def create(self,key,p):
                if key in self.rows:return False
                self.put(key,p);return True
            def req(self,method,params,body,prefer):
                assert method=='PATCH'
                key=params['cache_key'][3:];row=self.rows.get(key)
                if self.race or not row or params['updated_at']!='eq.'+row['updated_at']:return []
                self.put(key,body['payload']);return [self.row(key)]
        return C()
    def snapshot(self,cut,status='complete'):
        return dict(status=status,cabinet='token_3',slot_msk=cut.isoformat(),observed_at=cut.isoformat(),completed_at=cut.isoformat(),orders={str(n):dict(status='complete') for n in (0,1,7)},advertising=dict(status='complete'))
    def test_backup_skips_complete_hour_before_wb_identity_or_requests(self):
        clock=datetime.now(timezone.utc);cut=clock.astimezone(m.MSK).replace(minute=0,second=0,microsecond=0)
        c=self.cache();c.put(m.POLICY,dict(enabled=True,cabinet='token_3',wb_writes=0));c.put(m.slot_key(cut),self.snapshot(cut))
        with (patch.object(m,'Cache',return_value=c),patch.object(m,'ReadOnlyWB',side_effect=AssertionError('Repeated WB read')),patch.object(m,'validate_identity',side_effect=AssertionError('Repeated identity')),
              patch.dict('os.environ',GITHUB_REPOSITORY='Ekaterina11098/veschi-bot-runner')):
            m.run()
        self.assertEqual(c.get(m.ROOT+':latest')['source_key'],m.slot_key(cut))
    def test_active_lease_blocks_duplicate(self):
        c=self.cache();clock=datetime(2026,10,31,12,tzinfo=timezone.utc);cut=clock.astimezone(m.MSK)
        self.assertTrue(m.claim_slot(c,cut,'one',clock));self.assertFalse(m.claim_slot(c,cut,'two',clock+timedelta(minutes=5)))
    def test_crash_lease_recovers_only_after_timeout(self):
        c=self.cache();clock=datetime(2026,10,31,12,tzinfo=timezone.utc);cut=clock.astimezone(m.MSK)
        self.assertTrue(m.claim_slot(c,cut,'one',clock));self.assertTrue(m.claim_slot(c,cut,'two',clock+timedelta(minutes=13)))
        self.assertEqual(c.get(m.slot_key(cut)+':lease')['attempt'],2)
    def test_recovery_cas_race_loser_cannot_read(self):
        c=self.cache();clock=datetime(2026,10,31,12,tzinfo=timezone.utc);cut=clock.astimezone(m.MSK)
        m.claim_slot(c,cut,'one',clock);c.race=True
        self.assertFalse(m.claim_slot(c,cut,'two',clock+timedelta(minutes=13)))
    def test_attempts_are_bounded(self):
        c=self.cache();clock=datetime(2026,10,31,12,tzinfo=timezone.utc);cut=clock.astimezone(m.MSK)
        for n in range(3):self.assertTrue(m.claim_slot(c,cut,str(n),clock+timedelta(minutes=13*n)))
        self.assertFalse(m.claim_slot(c,cut,'four',clock+timedelta(minutes=40)))
    def test_partial_snapshot_preserved_while_recovery_is_selected(self):
        c=self.cache();cut=datetime(2026,10,31,15,tzinfo=m.MSK);key=m.slot_key(cut)
        original=self.snapshot(cut,'partial');c.put(key,original)
        recovered=self.snapshot(cut);source=key+':attempt:77';c.put(source,recovered);m.publish_latest(c,source,recovered)
        self.assertEqual(c.get(key),original);self.assertEqual(m.saved_slot(c,cut),(source,recovered))
    def test_slot_pointer_cannot_cross_hours(self):
        c=self.cache();cut=datetime(2026,10,31,15,tzinfo=m.MSK);c.put(m.slot_key(cut)+':latest',dict(source_key=m.slot_key(cut-timedelta(hours=1))))
        with self.assertRaises(ValueError):m.saved_slot(c,cut)
    def test_latest_cannot_regress_to_old_hour(self):
        c=self.cache();cut=datetime(2026,10,31,15,tzinfo=m.MSK)
        m.publish_latest(c,m.slot_key(cut),self.snapshot(cut))
        old=cut-timedelta(hours=1);m.publish_latest(c,m.slot_key(old),self.snapshot(old))
        self.assertEqual(c.get(m.ROOT+':latest')['slot_msk'],cut.isoformat())
    def test_msk_boundary_and_half_open_window(self):
        start = datetime(2026,10,31,0,tzinfo=m.MSK)
        end = start.replace(hour=13)
        rows = [dict(id=i,nmId=1,createdAt=t,convertedPrice=123,convertedCurrencyCode=156)
                for i,t in enumerate(['2026-10-30T20:59:59Z','2026-10-30T21:00:00Z','2026-10-31T09:59:59Z','2026-10-31T10:00:00Z'])]
        self.assertEqual([r['id'] for r in m.select_rows(rows,start,end)],[1,2])
    def test_unknown_currency_not_zero_or_mixed(self):
        a=m.aggregate([dict(id=1,convertedPrice=100,convertedCurrencyCode=643)])
        self.assertIsNone(a['amount_cny'])
        self.assertEqual(a['unknown_amount_ids'],[1])
    def test_money_native_minor_units(self):
        self.assertEqual(m.aggregate([dict(id=1,convertedPrice=12345,convertedCurrencyCode=156)])['amount_cny'],123.45)
    def test_cursor_nonadvance_rejected(self):
        d=datetime(2026,10,31,tzinfo=m.MSK)
        responses=iter([{'orders':[{'id':1}],'next':1},{'orders':[{'id':2}],'next':1}])
        with patch.object(m.time,'sleep'),self.assertRaises(ValueError):
            m.read_orders(lambda *a:next(responses),d,d.replace(hour=13))
    def test_pagination_dedup(self):
        d=datetime(2026,10,31,tzinfo=m.MSK)
        responses=iter([{'orders':[{'id':1}],'next':1},{'orders':[{'id':1},{'id':2}],'next':0}])
        with patch.object(m.time,'sleep'):
            self.assertEqual(set(m.read_orders(lambda *a:next(responses),d,d.replace(hour=13))),{1,2})
    def test_marketplace_write_endpoints_blocked(self):
        w=m.ReadOnlyWB()
        for path,method,write in [('/adv/v0/pause?id=1','GET',False),('/api/advert/v2/budget','POST',True),('/api/advert/v1/bids','PATCH',False)]:
            with self.assertRaises(ValueError):w.req(path,method,write=write)
        self.assertEqual(w.req('/api/advert/v2/budget','POST'),{'safe_read':True})
    def test_zero_baseline_no_fake_growth(self):
        self.assertIsNone(m.comparison({'count':4,'amount_cny':50},{'count':0,'amount_cny':0})['count']['pct'])
    def test_general_funnel_preserves_full_day_warning(self):
        reports=types.ModuleType('china_wb_evidence')
        reports.FUNNEL='read-only-funnel'
        class FakeReports:
            def __init__(self, adapter): pass
            def request(self, url, body):
                self_body=body
                return {'available':True,'observed_at':'2026-10-31T10:02:00+00:00',
                        'data':{'data':{'currency':'CNY','products':[{'product':{'nmId':143}}]}}}
        reports.Reports=FakeReports
        reports.normalize_funnel=lambda *a: [{'nm_id':143,'selected':{'clicks':772,'orders':3}}]
        with patch.dict(sys.modules,{'china_wb_evidence':reports}):
            result=m.collect_funnel(object(),datetime(2026,10,31,13,tzinfo=m.MSK),[143])
        self.assertTrue(result['past_period_is_full_day'])
        self.assertEqual(result['scope'],'all_sources')
        self.assertIn('2026-10-30T13',result['samehour_baseline_key'])
    def test_general_funnel_scope_is_bounded(self):
        reports=types.ModuleType('china_wb_evidence')
        reports.Reports=object; reports.FUNNEL='funnel';reports.normalize_funnel=lambda *a:None
        with patch.dict(sys.modules,{'china_wb_evidence':reports}):
            for scope in ([],list(range(6)),['143']):
                with self.assertRaises(ValueError):
                    m.collect_funnel(object(),datetime(2026,10,31,13,tzinfo=m.MSK),scope)

if __name__=='__main__':unittest.main()

