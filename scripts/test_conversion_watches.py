import copy
import unittest
from datetime import datetime, timezone
from conversion_watches import Worker, intent, parameters, next_due, unpack, report, PREFIX, DAILY, RECEIPTS

NOW=datetime(2026,10,17,17,30,tzinfo=timezone.utc)
CFG=dict(agent_id='china',chat_id=-123,owner_user_id=5,bot_id=9)

class Memory(Worker):
    def __init__(self,now=NOW):
        self.mem={};self.sent=[];self.now=now;self.collect=None
        self.transport=self.send;self.db=lambda *a,**k:[]
    def send(self,chat,text):
        self.sent.append((chat,text));return {'ok':True,'result':{'chat':{'id':chat},'message_id':len(self.sent)}}
    def get(self,key):return copy.deepcopy(self.mem.get(key))
    def save(self,key,value,insert=False):
        if insert and key in self.mem:return False
        self.mem[key]=copy.deepcopy(value);return True
    def config(self):return CFG
    def watches(self):return [(k,copy.deepcopy(v)) for k,v in self.mem.items() if k.startswith(PREFIX) and self.authorized(v)]
    def catalog(self):return [('987','52-NoelBag-fuchsia'),('988','52-NoelBag-black')]

def job(text,ident=1,**kw):return dict(id=ident,agent_id='china',chat_id=-123,sender_id=5,request_text=text,**kw)
CREATE='Следи за конверсией 52-NoelBag-fuchsia за последние 5 полных дней, присылай ежедневно в 12:00 МСК'

class Watches(unittest.TestCase):
    def test_parse_real_example(self):
        self.assertEqual(intent(CREATE),'create');self.assertEqual(parameters(CREATE),('12:00',5))
    def test_dash_time(self):self.assertEqual(parameters('за последние 4 дня ежедневно в 12-00'),('12:00',4))
    def test_conflicting_days(self):
        with self.assertRaises(ValueError):parameters('последние 5 дней за последние 4 дня')
    def test_bounds(self):
        for text in ('в 25:00','последние 15 дней','в ИП в 12:00'):
            with self.subTest(text=text),self.assertRaises(ValueError):parameters(text)
    def test_questions_do_not_create(self):self.assertEqual(intent('Как отслеживать конверсию ежедневно?'),'help')
    def test_unrelated_ignored(self):self.assertIsNone(intent('Покажи продажи за 5 дней'))
    def test_next_moscow_day(self):self.assertEqual(next_due('12:00',NOW),'2026-10-18T09:00:00+00:00')
    def test_next_same_day(self):self.assertEqual(next_due('23:00',NOW),'2026-10-17T20:00:00+00:00')
    def test_save_idempotent(self):
        w=Memory();a=w.command(job(CREATE));self.assertEqual(a,w.command(job(CREATE)));self.assertEqual(len(w.watches()),1)
        self.assertIn('уже активно',w.command(job(CREATE,2)));self.assertEqual(len(w.watches()),1)
    def test_no_guess_article(self):
        with self.assertRaises(ValueError):Memory().command(job(CREATE.replace('52-NoelBag-fuchsia','52')))
    def test_missing_time_not_saved(self):
        w=Memory()
        with self.assertRaises(ValueError):w.command(job('Следи за конверсией 52-NoelBag-fuchsia'))
        self.assertFalse(w.mem)
    def test_wrong_owner(self):
        j=job(CREATE);j['sender_id']=6
        with self.assertRaises(PermissionError):Memory().command(j)
    def test_cancel_update_replay(self):
        w=Memory();w.command(job(CREATE));key,v=w.watches()[0]
        text='Измени наблюдение '+v['id']+' на 13:15 за последние 4 дня'
        answer=w.command(job(text,2));self.assertEqual(answer,w.command(job(text,2)))
        self.assertEqual(w.get(key)['clock'],'13:15');self.assertEqual(w.get(key)['days'],4)
        w.command(job('Отмени наблюдение '+v['id'],3));self.assertEqual(w.get(key)['status'],'cancelled')
        self.assertEqual(w.reports(),0)
    def test_delivery_dedup(self):
        w=Memory();self.assertEqual(w.send_once('test',-123,'hello'),'sent');self.assertEqual(w.send_once('test',-123,'hello'),'sent');self.assertEqual(len(w.sent),1)
    def test_delivery_timeout_no_repeat(self):
        w=Memory()
        def fail(*args):raise TimeoutError()
        w.transport=fail;self.assertEqual(w.send_once('test',-123,'hello'),'uncertain')
        w.transport=w.send;self.assertEqual(w.send_once('test',-123,'hello'),'uncertain');self.assertFalse(w.sent)
    def test_confirmed_rate_limit_can_retry(self):
        w=Memory();w.transport=lambda *a:{'ok':False,'error_code':429,'parameters':{'retry_after':600}}
        self.assertEqual(w.send_once('test',-123,'hello'),'rejected');w.transport=w.send
        self.assertEqual(w.send_once('test',-123,'hello'),'waiting');w.now+=__import__('datetime').timedelta(minutes=11)
        self.assertEqual(w.send_once('test',-123,'hello'),'sent')
    def test_source_unknown_not_zero(self):
        obs=dict(scope_verified=True,status='received',arguments=dict(date_from='2026-10-16',date_to='2026-10-16',start_row=0),data={'data':{'data':[],'total':0,'need_update':0}})
        self.assertIsNone(unpack(obs,'2026-10-16','987','52-NoelBag-fuchsia'))
    def test_verified_zero_and_duplicates(self):
        row=dict(p_id=1,nm_id=987,sa_name='52-NoelBag-fuchsia',open_card_count=0,funnel_orders_count=0)
        obs=dict(scope_verified=True,status='received',arguments=dict(date_from='2026-10-16',date_to='2026-10-16',start_row=0),data={'data':{'data':[row],'total':1,'need_update':0}})
        self.assertEqual(unpack(obs,'2026-10-16','987','52-NoelBag-fuchsia')['views'],0)
        obs['data']['data'].update(data=[row,dict(row,p_id=2)],total=2)
        self.assertIsNone(unpack(obs,'2026-10-16','987','52-NoelBag-fuchsia'))
    def test_ratio_of_sums(self):
        w=Memory();w.command(job(CREATE));_,v=w.watches()[0];v['days']=2
        txt=report(v,{'2026-10-15':dict(orders=1,views=10),'2026-10-16':dict(orders=1,views=90)},NOW)
        self.assertIn('2,00% (2/100)',txt);self.assertNotIn('5,56%',txt)
    def test_partial_report(self):
        w=Memory();w.command(job(CREATE));_,v=w.watches()[0]
        txt=report(v,{},NOW);self.assertIn('Отчёт неполный: 5',txt);self.assertNotIn('За период:',txt)
    def test_initial_and_daily_no_duplicate(self):
        w=Memory();w.command(job(CREATE));key,v=w.watches()[0]
        w.load_days=lambda watch:({},[])
        self.assertEqual(w.reports(),1);self.assertEqual(w.reports(),0)
        w.now=datetime(2026,10,18,9,0,tzinfo=timezone.utc)
        self.assertEqual(w.reports(),1);self.assertEqual(w.reports(),0);self.assertEqual(len(w.sent),2)
    def test_source_outage_still_partial(self):
        w=Memory();w.command(job(CREATE));w.load_days=lambda watch:({},['2026-10-16'])
        def fail(*a):raise RuntimeError()
        w.collect=fail;self.assertEqual(w.reports(),1);self.assertIn('неполный',w.sent[0][1])

if __name__=='__main__':unittest.main()
