"""Frozen real-question model evaluation. No WB/TG, production writes or scheduling."""
import copy,json,os,re
from datetime import datetime,timezone
from unittest.mock import patch
from urllib.parse import urlparse
import requests
from china_cloud_cost_control import Cache
import china_analytic_dialog as a
from test_china_analytic_evidence import DialogIntegration
ROOT='china_agent:pavel_quality31:v1:'
def main():
 c=Cache();f=c.get(ROOT+'fixtures')
 if not f or not f.get('no_wb') or not f.get('no_telegram'):raise ValueError('Frozen private fixtures absent')
 output_key=ROOT+'model_results'
 if c.get(output_key):return
 base=copy.deepcopy(f['orders143'])
 # Keep its actual cutoff; frozen replay is not a current-data claim.
 ex=f['045_execution'];price=ex['prices'][0];stock=ex['stock']['rows'][0]
 sources={
 'orders143':base,
 'products023':f['products023'],
 'prices045':dict(source='WB exact seller price',cabinet='token_3',observed_at=ex['observed_at'],rows=[dict(nm_id=1473243895,article=price['vendorCode'],seller_price_cny=price['sizes'][0]['discountedPrice'])]),
 'stock045':dict(source='MSK exact COGS',cabinet='token_3',observed_at=ex['stock']['observed_at'],rows=[dict(article=stock['article'],cost_rub=stock['price']/100,stock=stock['stock'],reserve=stock['reserve'])])
 }
 cases=[
 dict(id='pavel198',question='Сколько сегодня на Гонконге заказов на модели 143?',expected_ids=[1473245494]),
 dict(id='orders_buyouts023',question='Заказы и выкупы 023-AlessiaBag-black за 2026-10-27 — 2026-10-30',expected_ids=[1473244984]),
 dict(id='economics045',question='045-NoelBag-ginger проверь эту сумку, точно в плюс продаем?',expected_ids=[1473243895])
 ]
 result=dict(status='running',model='gpt-6.1-sol',cases=[],wb_requests=0,telegram_sends=0,production_writes=0)
 original=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
 def guard(session,method,url,**kw):
  u=urlparse(url)
  if u.hostname=='api.openai.com' and u.path=='/v1/responses' and method.upper()=='POST':return original(session,method,url,**kw)
  raise PermissionError('Evaluation forbids external data reads and production writes')
 for case in cases:
  calls=[]
  class W:
   now=datetime.fromisoformat(f['fixed_now'])
   def __init__(self):
    self.mem={a.POLICY:dict(enabled=True,model='gpt-6.1-sol'),a.MEMORY:dict(revision=1),'china_agent:new_ad_economics_policy:v1':f['policy']}
   def catalog(self):return [('1473245494','143-ReginaBag-black'),('1473244984','023-AlessiaBag-black'),('1473243895','045-NoelBag-ginger')]
   def get(self,k):return copy.deepcopy(self.mem.get(k))
   def save(self,k,v):self.mem[k]=copy.deepcopy(v)
   def db(self,*args,**kwargs):return []
   def model_request(self,body):
    response=requests.post('https://api.openai.com/v1/responses',headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},json=body,timeout=150)
    if not response.ok:raise RuntimeError('Model HTTP '+str(response.status_code))
    return response.json()
  def live(an,topic,ids,first,last):
   calls.append(dict(topic=topic,nm_ids=ids,period=[first,last]))
   if ids!=case['expected_ids']:raise ValueError('Question scope mismatch')
   if topic=='orders' and ids==[1473245494]:return copy.deepcopy(sources['orders143'])
   if topic=='products' and ids==[1473244984]:return copy.deepcopy(sources['products023'])
   if ids==[1473243895] and topic in ['prices','stock']:return copy.deepcopy(sources[topic+'045'])
   return dict(available=False,source='frozen exact-period coverage check',note='Exact requested source/period unavailable in this frozen replay. Do not replace by zero or another period.')
  try:
   with patch.dict(__import__('sys').modules,DialogIntegration().modules()),patch.object(a.Analyst,'live',live),patch('requests.sessions.Session.request',guard):
    text,trace=a.answer(W(),dict(id=-31,chat_id=-1,request_text=case['question']),[])
   failures=[]
   if not calls or any(x['nm_ids']!=case['expected_ids'] for x in calls):failures.append('wrong_scope')
   if case['id']=='pavel198' and not (re.search(r'\b6\b',text) and re.search(r'выкуп|создан|FBS',text,re.I)):failures.append('orders_semantics')
   if case['id']=='orders_buyouts023' and not re.search(r'выкуп|продаж',text,re.I):failures.append('buyouts_missing')
   if case['id']=='economics045' and not re.search(r'предвар|нельзя|не.*подтверж|недостат|не.*доказ',text,re.I):failures.append('unsupported_profit')
   result['cases'].append(dict(id=case['id'],question=case['question'],answer=text,reads=calls,failures=failures))
  except Exception as ex:result['cases'].append(dict(id=case['id'],error=type(ex).__name__,reads=calls,failures=['exception']))
 result.update(status='completed',passed=sum(not r['failures'] for r in result['cases']),total=len(cases),completed_at=datetime.now(timezone.utc).isoformat())
 if not c.create(output_key,result) or c.get(output_key)!=result:raise ValueError('Immutable evaluation readback failed')
 print(json.dumps(dict(status=result['status'],passed=result['passed'],total=result['total'],wb_requests=0,telegram_sends=0)))
if __name__=='__main__':main()
