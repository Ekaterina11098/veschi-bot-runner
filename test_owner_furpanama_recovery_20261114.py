import unittest,sqlite3,sys,types
from unittest.mock import patch
from stock_operation_store import Store,canonical,digest,Stopped
import owner_furpanama_recovery_20261114 as m

class Tests(unittest.TestCase):
    def setUp(self):
        self.store=Store(sqlite3.connect(':memory:'));self.store.initialize_test_schema()
        self.store.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?)',(m.OLD,canonical({'article':m.ARTICLE}),'{}','hash','cloud',1))
        self.store.sql('INSERT INTO stock_operations VALUES(?,?,?,?,?)',(m.OLD,0,canonical(m.OLD_BODY),'prepared','uncertain'))
        self.store.sql('INSERT INTO stock_sku_locks VALUES(?,?)',(m.ARTICLE,m.OLD))
        self.store.sql('INSERT INTO stock_events VALUES(?,?,?,?,?,?)',('original-claim',m.OLD,0,'dispatch_claimed',2,'{}'))
        self.store.db.commit();self.data={'source':{'fbs':[{}, {},{m.ARTICLE:31}]}}
    def retire(self,actual):
        adapter=types.ModuleType('stock_batch_transport')
        adapter.SavedBatchAdapter=lambda *a:types.SimpleNamespace(read=lambda op:actual)
        with patch.dict(sys.modules,{'stock_batch_transport':adapter}),patch.object(m,'require_cloud_lease',lambda:None):
            m.retire_old(self.store,None,self.data,lambda **kw:None)
    def test_unknown_old_result_retired_without_replay(self):
        self.retire(31)
        self.assertEqual(self.store.operations(m.OLD)[0][2],'invalidated')
        self.assertEqual(self.store.operations(m.OLD)[0][1],m.OLD_BODY)
        self.assertEqual(self.store.sql("SELECT count(*) FROM stock_events WHERE state='dispatch_claimed'").fetchone()[0],1)
        self.assertEqual(self.data['source']['fbs'][2][m.ARTICLE],31)
        self.assertIsNone(self.store.sql('SELECT * FROM stock_sku_locks').fetchone())
    def test_matching_old_target_is_confirmed_by_read(self):
        self.retire(63);self.assertEqual(self.store.operations(m.OLD)[0][2],'confirmed')
    def test_foreign_lock_preserved(self):
        self.store.sql('UPDATE stock_sku_locks SET owner_run=?',(m.ROOT,))
        with self.assertRaises(Stopped):self.retire(31)
        self.assertEqual(self.store.operations(m.OLD)[0][2],'uncertain')
    def test_filter_preserves_original_times(self):
        source={'started':3,'moscow_raw':{m.ARTICLE:10,'other':9},'fbs':[{m.ARTICLE:1,'other':3}]*3,'unposted_orders':{'observed_at':4,'physical_observed_at':5,'available_moscow':{m.ARTICLE:8,'other':1}}}
        result=m.filtered(source);self.assertEqual(result['started'],3);self.assertEqual(result['unposted_orders']['observed_at'],4)
        self.assertEqual(result['moscow_raw'],{m.ARTICLE:10});self.assertIn('other',source['moscow_raw'])
    def test_guangzhou_or_foreign_article_write_rejected(self):
        for member in [{'article':m.ARTICLE,'operations':[{'cabinet':2}],'locations':[None,None,{'warehouse':2308581,'chrtId':2381216373}]},{'article':'other','operations':[]}]:
            with self.assertRaises(Stopped):m.validate_plan({'articles':[member]})

if __name__=='__main__':unittest.main()