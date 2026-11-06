import copy,json,unittest
from types import SimpleNamespace
from china_model_context import MODEL,pack,message
from china_codex_analysis import Core,POLICY
from china_codex_cloud import Worker,CLOUD

def unpack(v):
    if isinstance(v,dict):
        if v.get('encoding')=='columnar-v1':
            return [{k:unpack(x) for k,x in zip(v['columns'],row)} for row in v['rows']]
        return {k:unpack(x) for k,x in v.items()}
    if isinstance(v,list):return [unpack(x) for x in v]
    return v

class DB:
    def __init__(self):
        self.data={POLICY:dict(enabled=True,status='active',cabinet='token_3',chat_id=-1004342917488,wb_action_permission=False),'china_agent:shared_memory:policy:v1':dict(enabled=True)}
    def get(self,k):return copy.deepcopy(self.data.get(k))
    def once(self,k,v):
        if k in self.data:raise RuntimeError('Duplicate')
        self.data[k]=copy.deepcopy(v)
    def update(self,k,v,*args):self.data[k]=copy.deepcopy(v)
    def api(self,*args,**kwargs):return []

class Events:
    def with_result_collection(self):return self
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def __iter__(self):return iter([])
    def get_final_result(self):return SimpleNamespace(session_id='synthetic-sol')
class FakeWorker:
    def __init__(self):self.calls=0;self.creates=[];self.sent=None
    def sdk(self):return SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(create=self.create))))
    def create(self,**kw):self.creates.append(kw);return Events()
    def generate(self,sid,text,token):
        self.calls+=1;self.sent=json.loads(text);return '{"kind":"answer","answer":"ok"}'
    def recover(self,state):return None

class Tests(unittest.TestCase):
    def test_lossless_finance_and_unknowns_with_large_reduction(self):
        value={'rows':[dict(nm_id=i,profit=None if i%2 else -25.51,cost_price=1210,orders_count=40,sales_count=31,returns_count=0,financial_currency='RUB',observed_at='2026-11-06') for i in range(1000)]}
        packed=pack(value)
        self.assertEqual(value,unpack(packed))
        raw=len(json.dumps(value,ensure_ascii=False).encode());small=len(message(value).encode())
        self.assertLess(small,raw*.6)
        print('synthetic_finance_bytes',raw,small,'reduction_pct',round(100*(1-small/raw),2))
    def test_mixed_rows_nested_and_source_not_mutated(self):
        value=[{'id':1,'rows':[{'a':i,'b':None} for i in range(10)]},{'other':False}]
        before=copy.deepcopy(value);self.assertEqual(value,unpack(pack(value)));self.assertEqual(value,before)
    def test_cache_no_repeat_and_sol_only_new_work(self):
        db=DB();w=FakeWorker();core=Core(db,w)
        data={'facts':[dict(long_column_name=i,unknown_cost=None) for i in range(30)]}
        first,receipt=core.ask('same','analysis',data,{'kind':'answer'},lambda x:x)
        second,_=core.ask('same','analysis',data,{'kind':'answer'},lambda x:x)
        self.assertEqual(first,second);self.assertEqual(w.calls,1);self.assertEqual(len(w.creates),1)
        self.assertEqual(w.creates[0]['agent']['model'],MODEL);self.assertEqual(receipt['model'],MODEL)
        self.assertEqual(unpack(w.sent)['data'],data);self.assertFalse(unpack(w.sent)['wb_action_permission'])
    def test_uncertain_never_resubmitted(self):
        db=DB();w=FakeWorker()
        def fail(*args):w.calls+=1;raise TimeoutError()
        w.generate=fail;core=Core(db,w)
        for _ in range(2):
            with self.assertRaises(RuntimeError):core.ask('uncertain','analysis',{}, {},lambda x:x)
        self.assertEqual(w.calls,1);self.assertEqual(len(w.creates),1)
    def test_paid_guard_remains_closed(self):
        with self.assertRaises(PermissionError):Worker(DB()).sdk()
    def test_old_astra_session_is_not_reused_for_new_work(self):
        db=DB();db.data[CLOUD+'session']=dict(model='gpt-6-astra',session_id='historical')
        w=Worker(db);fake=FakeWorker();w.sdk=fake.sdk
        first=w.bootstrap();second=w.bootstrap()
        self.assertEqual(first,second);self.assertEqual(first['model'],MODEL)
        self.assertEqual(len(fake.creates),1);self.assertEqual(fake.creates[0]['agent']['model'],MODEL)
        self.assertEqual(db.data[CLOUD+'session']['session_id'],'historical')

if __name__=='__main__':unittest.main()
