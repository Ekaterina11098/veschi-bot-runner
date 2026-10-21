import os,sys,types,unittest
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
import china_search_analytics as s

NM='1473243898';ART='119-NoelBag-darkblack'
class Worker:
    def __init__(self):self.cache={};self.now=datetime.now(timezone.utc)
    def get(self,key):return self.cache.get(key)
    def save(self,key,value):self.cache[key]=value
    def catalog(self):return [(NM,ART)]
class Response:
    headers={}
    def __init__(self,code,data=None):self.status_code=code;self.data=data
    def json(self):return self.data
def envelope(field='items',**fields):
    return {'data':{'currency':'CNY',field:[{'nmId':int(NM),'vendorCode':ART,**fields}]}}

class SearchTests(unittest.TestCase):
    def test_zero_is_known_and_missing_not_zero(self):
        r=s.normalize(envelope(openCard={'current':0},rating=10,feedbackRating=5),NM,ART)['rows'][0]
        self.assertEqual(r['openCard'],0);self.assertIsNone(r['avgPosition']);self.assertIsNone(r['frequency'])
        self.assertEqual(r['rating'],10);self.assertEqual(r['feedbackRating'],5)
    def test_exact_product_and_currency(self):
        for data,nm,art in [(envelope(),123,ART),(envelope(),NM,'other')]:
            with self.assertRaises(ValueError):s.normalize(data,nm,art)
        data=envelope();data['data']['currency']='RUB'
        with self.assertRaises(ValueError):s.normalize(data,NM,ART)
    def test_product_and_phrase_shapes(self):
        self.assertEqual(len(s.normalize(envelope('products'),NM,ART)['rows']),1)
        self.assertEqual(len(s.normalize(envelope('items'),NM,ART)['rows']),1)
    def test_empty_does_not_fabricate(self):
        self.assertTrue(s.normalize({'data':{'currency':'CNY','items':[]}},NM,ART)['empty'])
    def test_full_day_windows(self):
        now=datetime(2026,10,21,12,tzinfo=timezone.utc)
        cur,prev=s.period('Проверь119',now)
        self.assertEqual(cur,{'start':'2026-10-14','end':'2026-10-20'})
        self.assertEqual(prev,{'start':'2026-10-07','end':'2026-10-13'})
        with self.assertRaises(ValueError):s.period('2026-10-20 2026-10-21',now)
    def test_read_allowlist_rejects_writes_redirects_and_bulk(self):
        body={'nmIds':[int(NM)]}
        self.assertTrue(s.allowed_read('POST',s.HOST+s.PATHS[0],body))
        for method,url,payload in [('PATCH',s.HOST+s.PATHS[0],body),('POST','https://advert-api.wildberries.ru/adv/v0/start',body),('POST',s.HOST+s.PATHS[0]+'?x=1',body),('POST',s.HOST+s.PATHS[0],{'nmIds':[1,2]})]:
            self.assertFalse(s.allowed_read(method,url,payload))
    def run_collect(self,responses):
        w=Worker();calls=[]
        def transport(url,**kw):
            self.assertTrue(s.allowed_read('POST',url,kw['json']));self.assertFalse(kw['allow_redirects']);calls.append(url)
            return responses.pop(0)
        req=types.SimpleNamespace(RequestException=RuntimeError)
        with patch.dict(os.environ,{'WB_TOKEN_3':'test-only'}),patch.dict(sys.modules,{'requests':req}):
            cur,prev=s.period('',w.now)
            result=s.collect(w,NM,ART,cur,prev,transport=transport,sleeper=lambda _:None)
            again=s.collect(w,NM,ART,cur,prev,transport=lambda *a,**k:self.fail('cache read made network call'),sleeper=lambda _:None)
        return result,w,calls,again
    def test_live_normalization_and_cache(self):
        r,w,calls,again=self.run_collect([Response(200,envelope('products',openCard={'current':9})),Response(200,envelope('items',text='клатч',openCard={'current':2}))])
        self.assertEqual(len(calls),2);self.assertTrue(r['complete']);self.assertEqual(r,again)
        self.assertEqual(r['product']['rows'][0]['openCard'],9);self.assertEqual(r['wb_writes'],0)
    def test_rate_limit_no_blind_retry(self):
        r,w,calls,_=self.run_collect([Response(429)])
        self.assertEqual(len(calls),1);self.assertFalse(r['available']);self.assertIn('blocked_until',w.get(s.RATE))
    def test_auth_denial_is_unavailable(self):
        r,_,calls,_=self.run_collect([Response(403)])
        self.assertFalse(r['available']);self.assertEqual(len(calls),1);self.assertIn('403',r['reason'])
    def test_other_cabinet_has_no_enrichment(self):
        self.assertEqual(s.context(Worker(),{'agent_id':'ip','request_text':'реклама119'},[]),(None,[]))

    def test_explicit_search_keeps_small_sample_and_missing_distinct(self):
        value={'available':True,'article':ART,'period':{'start':'2026-10-14','end':'2026-10-20'},
            'product':{'rows':[{'name':'Клатч без ремня','openCard':9,'addToCart':0,'orders':0,'avgPosition':50,'visibility':35}]},
            'queries':{'rows':[{'name':'Клатч без ремня','text':'клатч на ремешке','openCard':2,'orders':0,'avgPosition':2,'frequency':0}]}}
        answer=s.explicit_answer({'request_text':'Проверь поисковые запросы119'},[{'result':value}])
        self.assertIn('9',answer);self.assertIn('Выборка мала',answer);self.assertIn('Проверить комплектацию',answer)
        self.assertIn('не равны всем заказам',answer);self.assertNotIn('48%',answer);self.assertNotIn('скидку',answer)
        self.assertGreater(len(answer.splitlines()),5)
    def test_short_article_without_space_resolves_exact_product(self):
        with patch.object(s,'collect',return_value={'available':False}) as mocked:
            s.context(Worker(),{'agent_id':'china','request_text':'поисковые запросы артикула119'},[])
        self.assertEqual(mocked.call_args.args[1],NM)
    def test_plain_historical_conversion_stays_unchanged(self):
        self.assertEqual(s.context(Worker(),{'agent_id':'china','request_text':'Сравни конверсию119 за5дней'},[]),(None,[]))

if __name__=='__main__':unittest.main()