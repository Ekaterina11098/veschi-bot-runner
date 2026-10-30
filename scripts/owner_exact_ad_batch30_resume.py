"""Resume the exact scope after explicit owner waiver of stock/COGS refresh."""
import copy,json,os,sys
from datetime import datetime,timezone
import requests
import owner_exact_ad_batch30 as impl
BASE=impl.ROOT
ROOT='china_agent:owner_five_bid_actions:2026-10-30:v2'
SOURCE='china_agent:analytic_read:v1:86ea5b2333e49a6a2262494e4faa76a852eaa29ecbe8445a0ccda08b9b9197ea'
OriginalCache=impl.Cache
def source(c):
 a=c.get(ROOT+':approval') or {}
 if a.get('stock_refresh_waived_by_owner')is not True or a.get('owner_declares_stock_cogs_unchanged')is not True or a.get('stock_source_key')!=SOURCE:raise ValueError('Explicit stock/COGS refresh waiver missing')
 p=c.get(SOURCE) or {}
 if not str(p.get('observed_at','')).startswith('2026-10-30T') or p.get('cabinet')!='token_3' or not isinstance(p.get('rows'),list):raise ValueError('Dated original China stock source missing')
 return p
class ApprovedCache(OriginalCache):
 def put(self,key,p):
  if key==ROOT+':execution' and 'stock' in p:
   p=copy.deepcopy(p);s=source(self);p.update(stock_observed_at=s['observed_at'],stock_source_key=SOURCE,stock_refresh_waived_by_owner=True,stock_cogs_unchanged_is_owner_statement=True)
  return super().put(key,p)
def confirmed_stock(economy,articles):
 c=ApprovedCache();p=source(c);wanted={a.casefold() for a in articles};rows=[r for r in p['rows'] if (r.get('article')or'').casefold() in wanted]
 if len(rows)!=len(wanted) or {(r.get('article')or'').casefold() for r in rows}!=wanted:raise ValueError('Original stock snapshot lacks exact articles')
 return [dict(article=r['article'],stock=r.get('stock'),reserve=r.get('reserve'),price=r['cost_rub']*100 if isinstance(r.get('cost_rub'),(int,float)) else None) for r in rows]
def diagnostic():
 c=OriginalCache();key='china_agent:moysklad_read_check:2026-10-30:v1'
 e={'status':'reading','observed_at':impl.stamp(),'operations':[],'wb_writes':0,'moysklad_writes':0,'telegram_calls':0}
 if not c.create(key,e):print(json.dumps({'status':'diagnostic_already_recorded'}));return
 try:
  h={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN'],'Accept-Encoding':'gzip'};base='https://api.moysklad.ru/api/remap/1.2'
  r=requests.get(base+'/entity/store',headers=h,params={'limit':1000},timeout=45)
  e['operations'].append({'name':'stores','http_status':r.status_code})
  if not r.ok:raise ValueError('Stores HTTP '+str(r.status_code))
  j=r.json();stores=[s for s in j.get('rows',[]) if s.get('name')=='МСК' and not s.get('archived')]
  if j.get('meta',{}).get('size',999999)>len(j.get('rows',[])) or len(stores)!=1:raise ValueError('MSK store ambiguous or incomplete')
  params={'filter':'store='+stores[0]['meta']['href']+';stockMode=all;quantityMode=all','limit':1000,'offset':0}
  r=requests.get(base+'/report/stock/all',headers=h,params=params,timeout=55)
  try:j=r.json()
  except ValueError:j={}
  e['operations'].append({'name':'stock_report','http_status':r.status_code,'errors':[{'code':x.get('code'),'error':str(x.get('error',''))[:500]} for x in j.get('errors',[])],'rows_count':len(j.get('rows',[])),'size':j.get('meta',{}).get('size')})
  e['status']='ok' if r.ok and isinstance(j.get('rows'),list) else 'failed'
 except Exception as ex:e.update(status='failed',reason=str(ex) if isinstance(ex,ValueError) else type(ex).__name__)
 c.put(key,e);print(json.dumps({'status':e['status'],'operation_statuses':[{'name':x['name'],'http_status':x['http_status']} for x in e['operations']]}))
def run():
 prior=OriginalCache().get(BASE+':execution') or {}
 if prior.get('status')!='blocked' or prior.get('wb_writes')!=0 or prior.get('steps'):raise ValueError('Prior attempt not proved pre-write blocked')
 impl.ROOT=ROOT;impl.Cache=ApprovedCache;impl.fresh_stock=confirmed_stock;impl.run()
if __name__=='__main__':
 if len(sys.argv)==2 and sys.argv[1]=='diagnostic':diagnostic()
 elif len(sys.argv)==1:run()
 else:raise ValueError('Unsupported mode')
