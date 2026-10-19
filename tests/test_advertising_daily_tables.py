import copy,html,unittest
from datetime import datetime,timezone
from advertising_budget_evidence import render_daily_tables,deliver_daily_tables
class Store:
 def __init__(self):self.rows={}
 def db(self,method,table,params=None,body=None,prefer=None):
  if method=='GET':
   v=self.rows.get(params['cache_key'][3:])
   return [{'payload':v,'updated_at':'x'}] if v else []
  key=body['cache_key']
  if key in self.rows:return []
  self.rows[key]=copy.deepcopy(body['payload'])
  return [body]
 def cache_get(self,k):return copy.deepcopy(self.rows.get(k))
 def cache_set(self,k,v,ttl_days=0):self.rows[k]=copy.deepcopy(v)
class Tables(unittest.TestCase):
 def view(self):
  return dict(period='2026-10-18',observed_day='2026-10-19',campaigns=[
   dict(campaign_id=37363108,metrics_complete=True,spend=1100,revenue=11840,sku_order_basis='direct_only',above5=[],budget=dict(balance=8807,observed_at='2026-10-19T09:42:00+00:00',today_observation=True,valid=True)),
   dict(campaign_id=39410834,metrics_complete=True,spend=15101,revenue=227432,sku_order_basis='direct_only',above5=[dict(article='534-NoelBag-emerald',drr=11.51)],within5_count=9,budget={}),
   dict(campaign_id=40192945,metrics_complete=True,spend=0,revenue=0,sku_order_basis='direct_only',budget={}),
   dict(campaign_id=40428505,metrics_complete=True,spend=761,revenue=0,sku_order_basis='direct_only',status_id=11,budget=dict(balance=27816,observed_at='2026-10-19T05:21:00+00:00',today_observation=True,valid=True))])
 def test_two_tables_postclick_once(self):
  ms=render_daily_tables(self.view());self.assertEqual([m['kind'] for m in ms],['drr','budgets'])
  first=html.unescape(ms[0]['text']);self.assertIn('9,29%',first);self.assertIn('6,64%',first)
  self.assertIn('11,51%',first);self.assertIn('Без заказов',first);self.assertIn('Нет расхода',first)
  self.assertIn('19.10 12:42',ms[1]['text']);self.assertIn('Приостановлена',ms[1]['text'])
 def test_missing_not_normal(self):
  v=self.view();v['campaigns']=[dict(campaign_id=1,metrics_complete=False)]
  t=render_daily_tables(v)[0]['text'];self.assertIn('Нет данных',t);self.assertNotIn('Превышений нет',t.split('\n\n')[-2])
 def test_historical_not_current(self):
  v=self.view();v['campaigns'][0]['budget']['today_observation']=False
  self.assertIn('Исторический баланс',render_daily_tables(v)[1]['text'])
 def test_unknown_sku_basis(self):
  v=self.view();v['campaigns'][0]['sku_order_basis']='unknown'
  self.assertIn('Поартикульный прямой ДРР неизвестен',render_daily_tables(v)[0]['text'])
 def test_size_order(self):
  v=self.view();v['campaigns']=[dict(v['campaigns'][1],campaign_id=i,above5=[dict(article='Товар'+str(i),drr=8)]) for i in range(150)]
  ms=render_daily_tables(v)
  kinds=[x['kind'] for x in ms];self.assertEqual(kinds,sorted(kinds,key=lambda x:0 if x=='drr' else 1))
  for m in ms:self.assertLessEqual(len(html.unescape(m['text'][5:-6])),4096)
 def test_confirmed_never_resends(self):
  s=Store();messages=[dict(kind='drr',text='1'),dict(kind='budgets',text='2')];sent=[]
  def send(chat,text):sent.append(text);return dict(ok=True,chat_id=chat,message_id=len(sent))
  first=deliver_daily_tables(s,messages,55,'2026-10-19',send)
  second=deliver_daily_tables(s,messages,55,'2026-10-19',send)
  self.assertEqual(len(sent),2);self.assertEqual(first,second)
 def test_unknown_never_retries(self):
  s=Store();messages=[dict(kind='drr',text='1')];calls=[]
  def fail(chat,text):calls.append(text);raise TimeoutError()
  with self.assertRaises(TimeoutError):deliver_daily_tables(s,messages,55,'2026-10-19',fail)
  with self.assertRaises(RuntimeError):deliver_daily_tables(s,messages,55,'2026-10-19',fail)
  self.assertEqual(len(calls),1)
if __name__=='__main__':unittest.main()
