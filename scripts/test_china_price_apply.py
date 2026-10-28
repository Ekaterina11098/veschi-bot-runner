import copy,unittest
from china_price_apply import *

class Fake:
    def __init__(self):
        self.cache={};self.writes=0;self.state=3;self.fail=False;self.reads=0
        self.s=dict(action='Повышение',article='A',nm_id='1',current_cny='100',target_cny='110',seller_discount=50,base_cny=200,club_discount=0,editable_size_price=False)
        self.p=dict(nmID=1,vendorCode='A',currencyIsoCode4217='CNY',discount=50,clubDiscount=0,editableSizePrice=False,sizes=[dict(price=200,discountedPrice=100)])
        self.a=dict(schema_version=2,execution_authorized=True,execution_policy=POLICY,approval_policy='all_current_human_group_members',decision='approved_recommendation',chat_id=CHAT,bot_id=BOT,actor_user_id=7,report_job_id=57,report_date=day(),created_at=now().isoformat(),selections=[self.s])
        self.key=PREFIX+str(CHAT)+':57:7:'+'a'*64;self.cache[self.key]=self.a
    def get(self,k):return copy.deepcopy(self.cache.get(k))
    def create(self,k,p):
        if k in self.cache:return False
        self.cache[k]=copy.deepcopy(p);return True
    def put(self,k,p):self.cache[k]=copy.deepcopy(p)
    def validate(self,a):pass
    def capability(self):return {'wb_writes':0}
    def prices(self,ids):self.reads+=1;return {'1':copy.deepcopy(self.p)}
    def wb(self,path,method='GET',body=None):
        if method=='POST':
            self.writes+=1
            if self.fail:raise TimeoutError()
            self.p['sizes']=[dict(price=220,discountedPrice=110)]
            return dict(id=77,alreadyExists=False)
        if 'history/tasks' in path:return dict(uploadID=77,status=self.state)
        return dict(uploadID=77,historyGoods=[dict(nmID=1,errorText='quarantine' if self.state==6 else '')])
class Tests(unittest.TestCase):
    def runio(self,f):return process(f,f.key,polls=1,pause=lambda _:None)
    def test_apply_and_retry(self):
        f=Fake();e=self.runio(f);self.assertEqual(e['items'][0]['status'],'applied');self.runio(f);self.assertEqual(f.writes,1)
    def test_second_actor(self):
        f=Fake();self.runio(f)
        a=copy.deepcopy(f.a);a['actor_user_id']=8;k=PREFIX+str(CHAT)+':57:8:'+'a'*64;f.cache[k]=a
        e=process(f,k,polls=1);self.assertEqual(e['items'][0]['status'],'already_at_target');self.assertEqual(f.writes,1)
    def test_stale(self):
        f=Fake();f.p['sizes'][0]['discountedPrice']=101;e=self.runio(f)
        self.assertEqual(e['items'][0]['status'],'blocked');self.assertEqual(f.writes,0)
    def test_discount_change_stale(self):
        f=Fake();f.p['discount']=49;self.runio(f);self.assertEqual(f.writes,0)
    def test_timeout_no_repeat(self):
        f=Fake();f.fail=True;self.assertEqual(self.runio(f)['status'],'uncertain');self.runio(f);self.assertEqual(f.writes,1)
    def test_submitting_crash(self):
        f=Fake();ek='china_agent:price_execution:v1:'+f.key[len(PREFIX):];f.cache[ek]=dict(status='submitting')
        self.assertEqual(self.runio(f)['status'],'uncertain');self.assertEqual(f.writes,0)
    def test_uncertain_cross_actor_lock(self):
        f=Fake();f.cache['china_agent:price_write_lock:v1:1']=dict(status='uncertain',execution='other')
        self.runio(f);self.assertEqual(f.writes,0)
    def test_quarantine_not_success(self):
        f=Fake();f.state=6;e=self.runio(f);self.assertEqual(e['items'][0]['status'],'failed')
        self.assertEqual(f.cache['china_agent:price_write_lock:v1:1']['status'],'uncertain')
    def test_pending_resume_without_post(self):
        f=Fake();f.state=1;self.assertEqual(self.runio(f)['status'],'submitted');f.state=3;self.runio(f);self.assertEqual(f.writes,1)
    def test_old_record_refused(self):
        f=Fake();f.cache[f.key]['execution_authorized']=False
        with self.assertRaises(ValueError):self.runio(f)
        self.assertEqual(f.writes,0)
    def test_wrong_day(self):
        f=Fake();f.cache[f.key]['report_date']='2026-01-01'
        with self.assertRaises(ValueError):self.runio(f)
    def test_exact_discount_rollback(self):
        f=Fake();s=dict(f.s,action='Снижение',current_cny='106.6',target_cny='82',base_cny=164,seller_discount=35)
        p=dict(f.p,discount=35,sizes=[dict(price=164,discountedPrice=106.6)])
        self.assertEqual(plan(s,p),dict(nmID=1,price=164,discount=50))
    def test_no_approximate(self):
        f=Fake();s=dict(f.s,target_cny='110.123')
        with self.assertRaises(ValueError):plan(s,f.p)
    def test_cny_and_size_gate(self):
        f=Fake()
        for p in [dict(f.p,currencyIsoCode4217='RUB'),dict(f.p,editableSizePrice=True),dict(f.p,vendorCode='other')]:
            with self.assertRaises(ValueError):plan(f.s,p)
    def test_no_selected_extra_write(self):
        f=Fake();e=self.runio(f)
        self.assertEqual(e['request'],dict(data=[dict(nmID=1,price=220,discount=50)]))
    def test_notice_once_and_uncertain_no_repeat(self):
        f=Fake();f.sends=0
        def tg(method,body):
            f.sends+=1;raise TimeoutError()
        f.tg=tg;e=self.runio(f);notify(f,f.key,e);notify(f,f.key,e);self.assertEqual(f.sends,1)
    def test_changed_while_preparing(self):
        f=Fake();ek='china_agent:price_execution:v1:'+f.key[len(PREFIX):]
        f.cache[ek]=dict(status='preflight',items=[dict(selection=f.s,request=dict(nmID=1,price=220,discount=50),status='ready',lock='lock')])
        f.p['sizes'][0]['discountedPrice']=101;self.runio(f);self.assertEqual(f.writes,0)
if __name__=='__main__':unittest.main()

class BulkReadTests(unittest.TestCase):
    def test_bulk_read_once_and_only_requested(self):
        io=IO.__new__(IO);calls=[]
        def wb(path):calls.append(path);return dict(listGoods=[dict(nmID=n) for n in range(1,14)])
        io.wb=wb
        self.assertEqual(set(io.prices([str(n) for n in range(1,12)])),{str(n) for n in range(1,12)})
        self.assertEqual(len(calls),1)
    def test_missing_bulk_card_fails(self):
        io=IO.__new__(IO);io.wb=lambda path:dict(listGoods=[])
        with self.assertRaises(ValueError):io.prices([str(n) for n in range(11)])
