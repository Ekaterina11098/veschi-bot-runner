import hashlib,sys,types,unittest
from datetime import date,datetime,timezone
from unittest.mock import patch
from china_price_delivery import deliver,rows

class Delivery(unittest.TestCase):
    def worker(self,n):
        answer='\n\n'.join('Повышение · '+str(i)+'-Bag-black Продавец: 100 → 105 ¥\nПокупатель: 1000 → 1050 ₽' for i in range(n))
        return types.SimpleNamespace(job=dict(id=280,answer=answer,tool_trace=[]),chat=-1004342917488,day=date(2026,11,9),now=datetime(2026,11,9,19,tzinfo=timezone.utc),mode='morning',audit={},uncertain=False,patch=lambda b:[b],get=lambda k:{})
    def run_delivery(self,w,db=None,fail=False):
        db={} if db is None else db;calls=[]
        class Cache:
            def get(self,k):return db.get(k)
            def create(self,k,v):
                if k in db:return False
                db[k]=v;return True
            def put(self,k,v):db[k]=v
        def http(session,method,url,**kw):
            action=url.rsplit('/',1)[-1];calls.append(action)
            if action=='getMe':v={'id':8780468043}
            else:
                if fail:raise TimeoutError()
                v={'chat':{'id':w.chat},'message_id':900}
            return types.SimpleNamespace(ok=True,status_code=200,json=lambda:{'ok':True,'result':v})
        w.original_http=http
        modules={'requests':types.SimpleNamespace(Session=lambda:None),
                 'china_cloud_cost_control':types.SimpleNamespace(Cache=Cache,stamp=lambda:'2026-11-09T16:00:00Z'),
                 'china_table_png':types.SimpleNamespace(render=lambda *a,**kw:[b'PNG']),
                 'china_agent':types.ModuleType('china_agent'),
                 'china_agent.price_brief':types.SimpleNamespace(plain_payload=lambda *a:{})}
        with patch.dict(sys.modules,modules),patch.dict('os.environ',{'CHINA_TELEGRAM_BOT_TOKEN':'test'}):
            deliver(w)
        return db,calls
    def test_six_rows_png_bound_to_full_answer_and_no_writes(self):
        w=self.worker(6);db,calls=self.run_delivery(w)
        self.assertEqual(calls,['getMe','sendPhoto'])
        bind=db['china_agent:price_report_message:v1:900']
        self.assertEqual(bind['report_sha256'],hashlib.sha256(w.job['answer'].encode()).hexdigest())
        self.assertEqual(bind['selection_count'],6)
        self.assertFalse(bind['execution_authorized'])
    def test_same_report_reuses_receipt(self):
        w=self.worker(6);db,_=self.run_delivery(w)
        _,calls=self.run_delivery(w,db)
        self.assertEqual(calls,['getMe'])
    def test_unknown_outcome_blocks_resend(self):
        w=self.worker(6);db={}
        with self.assertRaisesRegex(RuntimeError,'uncertain'):self.run_delivery(w,db,True)
        with self.assertRaisesRegex(RuntimeError,'no replay'):self.run_delivery(w,db)
    def test_two_line_rows_preserve_buyer(self):
        w=self.worker(1)
        self.assertEqual(rows(w.job['answer'])[0],['Повышение','0-Bag-black','100 → 105 ¥','1000 → 1050 ₽'])
if __name__=='__main__':unittest.main()

