import importlib.util
import sys
import types
import unittest
from datetime import datetime
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

if __name__=='__main__':unittest.main()

