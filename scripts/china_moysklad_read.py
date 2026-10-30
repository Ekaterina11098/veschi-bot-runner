"""Read-only, bounded MoySklad stock/COGS transport; missing rows are never zero.
Product filters: https://raw.githubusercontent.com/moysklad/api-remap-1.2-doc/master/md/reports/_report_stock.md
"""
import os,re,time
from datetime import datetime,timezone
import requests
BASE='https://api.moysklad.ru/api/remap/1.2'
class MoySkladReadError(ValueError):pass
class Reader:
 def __init__(self,token=None,get=None,sleep=None):
  self.token=token if token is not None else os.environ['MOYSKLAD_API_TOKEN']
  self.get_request=get or requests.get;self.sleep=sleep or time.sleep;self.read_attempts=0
 def get(self,path,params):
  if path not in ['/entity/store','/entity/product','/report/stock/all']:raise MoySkladReadError('Read endpoint not allowed')
  headers={'Authorization':'Bearer '+self.token,'Accept-Encoding':'gzip','Accept':'application/json;charset=utf-8'}
  for attempt in range(3):
   self.read_attempts+=1
   try:r=self.get_request(BASE+path,params=params,headers=headers,timeout=(10,40),allow_redirects=False)
   except (requests.exceptions.ConnectionError,requests.exceptions.Timeout):
    if attempt==2:raise MoySkladReadError('MoySklad read connection failed after 3 attempts') from None
    self.sleep(2*(attempt+1));continue
   if r.status_code==429 or 500<=r.status_code<=599:
    if attempt==2:raise MoySkladReadError('MoySklad read HTTP '+str(r.status_code)+' after 3 attempts')
    self.sleep(2*(attempt+1));continue
   if not 200<=r.status_code<=299:raise MoySkladReadError('MoySklad read HTTP '+str(r.status_code))
   try:j=r.json()
   except ValueError:raise MoySkladReadError('MoySklad returned invalid JSON') from None
   if not isinstance(j,dict) or j.get('errors'):raise MoySkladReadError('MoySklad read API error')
   return j
 def pages(self,path,params):
  rows=[];offset=0;advertised=None
  while True:
   j=self.get(path,dict(params,limit=100,offset=offset));part=j.get('rows');size=j.get('meta',{}).get('size')
   if not isinstance(part,list) or type(size)is not int or size<0:raise MoySkladReadError('MoySklad page completeness unknown')
   if advertised is not None and size!=advertised:raise MoySkladReadError('MoySklad page coverage changed during read')
   advertised=size
   if any(not isinstance(r,dict) for r in part) or len(rows)+len(part)>size:raise MoySkladReadError('MoySklad page malformed')
   rows+=part;offset+=len(part)
   if offset==size:return rows
   if not part or offset>=50000:raise MoySkladReadError('MoySklad pagination incomplete')
 def stock(self,articles):
  if not isinstance(articles,(list,tuple)) or not articles or len(articles)>1000 or any(not isinstance(a,str) or not a.strip() or any(ch in a for ch in ';=\r\n') for a in articles):raise MoySkladReadError('Exact article scope required')
  wanted={a.casefold():a for a in articles}
  if len(wanted)!=len(articles):raise MoySkladReadError('Duplicate article scope')
  stores=[s for s in self.pages('/entity/store',{}) if s.get('name')=='МСК' and not s.get('archived')]
  if len(stores)!=1:raise MoySkladReadError('MSK warehouse ambiguous')
  store=stores[0].get('meta',{}).get('href','')
  if not re.fullmatch(re.escape(BASE)+r'/entity/store/[0-9a-f-]{36}',store):raise MoySkladReadError('Invalid MSK store identity')
  products=[]
  if len(wanted)<=20:
   for article in articles:products+=self.pages('/entity/product',{'filter':'article='+article})
  else:products=self.pages('/entity/product',{})
  mapped={};missing=[]
  for key,article in wanted.items():
   ps=[p for p in products if str(p.get('article','')).casefold()==key]
   # Exact article scope cannot pick one of several variants or duplicate cards.
   if len(ps)!=1:missing.append({'article':article,'reason':'product_missing' if not ps else 'product_ambiguous'});continue
   p=ps[0];href=p.get('meta',{}).get('href','')
   if not re.fullmatch(re.escape(BASE)+r'/entity/product/[0-9a-f-]{36}',href):raise MoySkladReadError('Invalid product identity')
   mapped[key]=href
  reports=[];entries=list(mapped.items())
  for start in range(0,len(entries),20):
   group=entries[start:start+20]
   filt='store='+store+';stockMode=all;quantityMode=all'+''.join(';product='+href for _,href in group)
   rows=self.pages('/report/stock/all',{'filter':filt});allowed={href for _,href in group}
   if any(r.get('meta',{}).get('href','').split('?')[0] not in allowed for r in rows):raise MoySkladReadError('Stock report outside exact product filter')
   reports+=rows
  out=[]
  for key,href in mapped.items():
   matched=[r for r in reports if str(r.get('article','')).casefold()==key and r.get('meta',{}).get('href','').split('?')[0]==href]
   if len(matched)!=1:missing.append({'article':wanted[key],'reason':'report_row_missing' if not matched else 'report_row_ambiguous'});continue
   r=matched[0]
   out.append({k:r.get(k) for k in ['article','stock','reserve','price']})
  return {'rows':out,'missing_articles':missing,'observed_at':datetime.now(timezone.utc).isoformat(),'warehouse':'МСК','warehouse_id':stores[0].get('id'),'read_attempts':self.read_attempts,'coverage_complete':not missing,'moysklad_writes':0,'wb_calls':0,'telegram_calls':0}
def read_stock(articles):return Reader().stock(articles)
