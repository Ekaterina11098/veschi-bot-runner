import unittest,sqlite3,sys,types,contextvars,copy
from unittest.mock import patch
from stock_operation_store import Store,Stopped

china=types.ModuleType('stock_china_mgt')
PAUSE={'wb_warehouse_id':2308581,'wb_cabinet':2,'publication_enabled':False,'mode':'owner_paused'}
china.policy=lambda:dict(PAUSE)
def qty(v):
    if type(v) is not int or v<0:raise Stopped('unknown quantity')
    return v
china.qty=qty;sys.modules['stock_china_mgt']=china
transport=types.ModuleType('stock_cloud_execution');transport._INTENT=contextvars.ContextVar('test-intent',default=None)
sys.modules['stock_cloud_execution']=transport
import stock_guangzhou_owner_zero as z

class Fake:
    WB_CONTENT='https://content-api.wildberries.cn';WB_MARKET='https://marketplace-api.wildberries.cn'
    norm=staticmethod(lambda x:str(x or '').strip().lower())
    cabinet_tokens=staticmethod(lambda:['one','two','three'])
    STOCK_REQUEST_GATE=types.SimpleNamespace(wait_ready=lambda *a:None)
    def __init__(self):self.values={11:5,12:0,13:2};self.writes=[];self.fail=False
    def api(self,method,url,token,**kw):
        assert token=='three'
        if url.endswith('/warehouses'):return [{'id':2308581,'name':'Гуанчжоу'}]
        if '/cards/' in url:
            cards=[{'vendorCode':'a','nmID':1,'sizes':[{'chrtID':11}]},{'vendorCode':'b','nmID':2,'sizes':[{'chrtID':12}]}] if url.endswith('/list') else [{'vendorCode':'c','nmID':3,'sizes':[{'chrtID':13}]}]
            return {'cards':cards,'cursor':{'total':len(cards)}}
        assert url.endswith('/stocks/2308581')
        if method=='POST':return {'stocks':[{'chrtId':i,'amount':self.values[i]} for i in kw['json']['chrtIds'] if i in self.values]}
        assert method=='PUT'
        intent=transport._INTENT.get();z.validate_intent(intent)
        self.writes.append(copy.deepcopy(kw['json']))
        if self.fail:raise RuntimeError('lost response')
        for row in kw['json']['stocks']:self.values[row['chrtId']]=row['amount']
        return {}

class Tests(unittest.TestCase):
    def setUp(self):
        self.store=Store(sqlite3.connect(':memory:'));self.store.initialize_test_schema();self.g=Fake()
        self.lease=patch.object(z,'require_cloud_lease',lambda:None);self.lease.start()
    def tearDown(self):self.lease.stop()
    def test_backup_zero_and_no_replay(self):
        result=z.execute(self.g,self.store)
        self.assertTrue(result['execution_complete']);self.assertEqual(result['previous_units'],7)
        self.assertEqual([r['amount'] for r in result['backup']],[5,0,2]);self.assertEqual(set(self.g.values.values()),{0})
        self.assertEqual(len(self.g.writes),1);self.assertEqual(result,z.execute(self.g,self.store));self.assertEqual(len(self.g.writes),1)
    def test_uncertain_never_resends(self):
        self.g.fail=True
        with self.assertRaises(RuntimeError):z.execute(self.g,self.store)
        self.assertEqual(len(self.g.writes),1)
        with self.assertRaises(Stopped):z.execute(self.g,self.store)
        self.assertEqual(len(self.g.writes),1)
        self.g.values={11:0,12:0,13:0};self.g.fail=False
        self.assertTrue(z.execute(self.g,self.store)['execution_complete']);self.assertEqual(len(self.g.writes),1)
    def test_active_policy_blocks_before_calls(self):
        with patch.object(z,'policy',lambda:dict(PAUSE,publication_enabled=True)):
            with self.assertRaises(Stopped):z.execute(self.g,self.store)
        self.assertFalse(self.g.writes);self.assertIsNone(z.saved(self.store))
    def test_foreign_warehouse_blocks(self):
        original=self.g.api
        self.g.api=lambda m,u,t,**k:[{'id':2126188,'name':'Гуанчжоу'}] if u.endswith('/warehouses') else original(m,u,t,**k)
        with self.assertRaises(Stopped):z.execute(self.g,self.store)
        self.assertFalse(self.g.writes)
    def test_backup_precedes_write(self):
        original=self.g.api
        def api(m,u,t,**k):
            if m=='PUT':
                root=z.saved(self.store);self.assertEqual(root['backup_digest'],z.digest(root['backup']))
                self.assertEqual(len(root['backup']),3)
            return original(m,u,t,**k)
        self.g.api=api;z.execute(self.g,self.store)
    def test_increase_payload_denied(self):
        original=self.g.api
        def api(m,u,t,**k):
            if m=='PUT':transport._INTENT.get()['stocks'][0]['amount']=99
            return original(m,u,t,**k)
        self.g.api=api
        with self.assertRaises(Stopped):z.execute(self.g,self.store)
        self.assertFalse(self.g.writes)

if __name__=='__main__':unittest.main()