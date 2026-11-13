"""Exact143 common-MSK-pool audit. Only read endpoints; no queue/policy changes."""
import json,os,re,time,math
from datetime import datetime,timezone
from collections import Counter
from urllib.parse import urlparse
import requests
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
from china_moysklad_read import Reader,BASE
ROOT='china_agent:owner_143_pool:2026-11-13:v1';ART='143-reginabag-black';STORE='3c67619d-f25d-11ee-0a80-0c6f000a027a'
WAREHOUSES=[1863255,854652,2126188];SIZES=[1280289308,482086996,2205272030]
def run():
 c=Cache();req=c.get(ROOT+':request')or{}
 if req.get('readonly')is not True or req.get('article')!=ART:raise ValueError('Exact request')
 if (c.get(ROOT)or{}).get('status')=='complete':return
 validate_identity(c,WB());original=requests.sessions.Session.request
 def guard(session,method,url,**kw):
  u=urlparse(url);m=method.upper();body=kw.get('json')or{}
  private=url.startswith(c.url)and u.path.endswith('/telegram_api_cache')and m in ['GET','POST','PATCH']
  ms=m=='GET'and u.hostname=='api.moysklad.ru'and u.path.startswith('/api/remap/1.2/')and u.path.split('/')[4]in ['entity','report']
  wb=u.hostname=='marketplace-api.wildberries.ru'and ((m=='GET'and u.path in ['/api/v3/orders','/api/v3/orders/new'])or(m=='POST'and(u.path=='/api/v3/orders/status'or u.path in ['/api/v3/stocks/'+str(w)for w in WAREHOUSES])))
  oz=url==os.environ['SUPABASE_URL'].rstrip('/')+'/functions/v1/stock-ozon-read'and m=='POST'and body.get('path')in ['/v4/posting/fbs/list','/v2/product/info/stocks-by-warehouse/fbs']
  if not(private or ms or wb or oz):raise ValueError('Read-only audit guard')
  return original(session,method,url,**kw)
 requests.sessions.Session.request=guard
 result=c.get(ROOT)or dict(status='reading',created_at=stamp(),inputs={},errors={},wb_writes=0,moysklad_writes=0,telegram_calls=0,model_calls=0,grants_action_permission=False)
 def save():
  v=json.loads(json.dumps(result))
  if c.get(ROOT):c.put(ROOT,v)
  else:c.create(ROOT,v)
 def stage(name,fn):
  if name in result['inputs']:return
  try:result['inputs'][name]=fn()
  except Exception as ex:result['errors'][name]=str(ex)[:180]if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__
  save()
 def call(method,url,body=None,params=None,token=None,headers=None):
  r=requests.request(method,url,json=body,params=params,headers=headers or{'Authorization':token},timeout=50)
  if not r.ok:raise ValueError('Read HTTP '+str(r.status_code))
  return r.json()
 tokens=[os.environ['WB_TOKEN_'+str(i)]for i in [1,2,3]]
 def wb(i,path,body=None,params=None):return call('POST'if body is not None else'GET','https://marketplace-api.wildberries.ru'+path,body,params,tokens[i])
 def wborders(i):
  found={};cursor=0
  for page in range(12):
   j=wb(i,'/api/v3/orders',params={'limit':1000,'next':cursor,'dateFrom':int(datetime(2026,11,11,tzinfo=timezone.utc).timestamp()),'dateTo':int(time.time())});part=j.get('orders')
   if not isinstance(part,list):raise ValueError('WB page')
   for r in part:
    if str(r.get('article','')).casefold()==ART and r.get('warehouseId')==WAREHOUSES[i]:found[r['id']]=r
   if not part or not j.get('next'):break
   if cursor==j['next']:raise ValueError('WB cursor')
   cursor=j['next']
  else:raise ValueError('WB pagination')
  for r in wb(i,'/api/v3/orders/new')['orders']:
   if str(r.get('article','')).casefold()==ART and r.get('warehouseId')==WAREHOUSES[i]:found[r['id']]=r
  old={int(u['id'])for u in req['pending']if u['cabinet']==i}
  if not old<=set(found):raise ValueError('Outstanding order missing')
  ids=sorted(found);states=wb(i,'/api/v3/orders/status',{'orders':ids})['orders']if ids else[]
  if {r['id']for r in states}!=set(ids):raise ValueError('Status coverage')
  status={r['id']:r for r in states};known={(x[0],str(x[1]))for x in req['known_ids']};units=[]
  for ident,r in found.items():
   if ident not in old and (i,str(ident))in known:continue
   s=status[ident];supplier=s.get('supplierStatus');ws=s.get('wbStatus');cancel=supplier=='cancel'or(supplier in ['new','confirm']and ws in ['declined_by_client','canceled'])
   if supplier not in ['new','confirm','complete','cancel','cancel_carrier']:raise ValueError('Unknown WB status')
   units.append(dict(cabinet=i,id=str(ident),article=ART,quantity=1,group='wb:'+str(r['supplyId'])if r.get('supplyId')else'wb:'+str(i)+':order:'+str(ident),supplier_status=supplier,wb_status=ws,cancelled_before_ship=cancel,created_at=r['createdAt']))
  return dict(observed_at=stamp(),units=units,found143=len(found))
 def oz(path,body):
  j=call('POST',os.environ['SUPABASE_URL'].rstrip('/')+'/functions/v1/stock-ozon-read',{'path':path,'body':body},headers={'x-stock-backend-key':os.environ['SUPABASE_SECRET_KEY']})
  if j.get('upstream_status')!=200:raise ValueError('Ozon read '+str(j.get('upstream_status')))
  return j['data']
 def ozorders():
  cursor='';out=[];known={(x[0],str(x[1]))for x in req['known_ids']}
  for page in range(12):
   j=oz('/v4/posting/fbs/list',{'dir':'ASC','filter':{'since':'2026-11-11T00:00:00+00:00','to':stamp()},'limit':100,'cursor':cursor,'with':{'analytics_data':False,'financial_data':False}})
   if not isinstance(j.get('postings'),list):raise ValueError('Ozon postings')
   for r in j['postings']:
    for p in r.get('products',[]):
     if str(p.get('offer_id','')).casefold()!=ART:continue
     if (3,str(r['posting_number']))in known and not any(u['cabinet']==3 and u['id']==r['posting_number']for u in req['pending']):continue
     if r.get('parent_posting_number'):raise ValueError('Ozon split requires reconciliation')
     cancel=r['status']in ['canceled','cancelled']and r.get('cancellation',{}).get('cancelled_after_ship')is False
     out.append(dict(cabinet=3,id=r['posting_number'],group='ozon:'+r['posting_number'],quantity=p['quantity'],article=ART,status=r['status'],cancelled_before_ship=cancel,created_at=r.get('in_process_at')))
   if j.get('has_next')is False:return dict(observed_at=stamp(),units=out)
   nxt=j.get('cursor')
   if not nxt or nxt==cursor:raise ValueError('Ozon cursor')
   cursor=nxt
  raise ValueError('Ozon page bound')
 reader=Reader()
 def msget(path,params):
  return call('GET',BASE+path,params=params,headers={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN'],'Accept-Encoding':'gzip'})
 def pages(path,params):
  out=[]
  for offset in range(0,6000,1000):
   j=msget(path,dict(params,limit=1000,offset=offset));part=j.get('rows');size=j.get('meta',{}).get('size')
   if not isinstance(part,list)or type(size)is not int:raise ValueError('MS coverage')
   out+=part
   if len(out)==size:return out
   if not part:raise ValueError('MS incomplete')
  raise ValueError('MS bounded pages')
 def documents():
  prods=pages('/entity/product',{'filter':'article=143-ReginaBag-black'});prods=[p for p in prods if str(p.get('article','')).casefold()==ART]
  if len(prods)!=1:raise ValueError('Exact product identity')
  href=prods[0]['meta']['href'];headers=pages('/entity/demand',{'filter':'updated>=2026-11-11 00:00:00;applicable=true;store='+BASE+'/entity/store/'+STORE});orders=pages('/entity/customerorder',{'filter':'updated>=2026-11-11 00:00:00'});orders={r['id']:r for r in orders}
  units=sum([v['units']for k,v in result['inputs'].items()if k.startswith('orders:')],[]);groups={u['group']for u in units};docs=[]
  for d in headers:
   ref=d.get('customerOrder',{}).get('meta',{}).get('href','');o=orders.get(ref.rsplit('/',1)[-1],{})
   if ref and not o:o=call('GET',ref,headers={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN'],'Accept-Encoding':'gzip'})
   text=' '.join(str(v or'')for v in [d.get('name'),d.get('externalCode'),d.get('description'),o.get('name'),o.get('description')]);wbgi=set(re.findall(r'WB-GI-\d+',text));ozids=set(re.findall(r'(?<![\w-])\d{5,}-\d{3,}-\d+(?![\w-])',text));matched={g for g in groups if(g.startswith('wb:')and g[3:]in wbgi)or(g.startswith('ozon:')and g[5:]in ozids)}
   if not matched:continue
   if len(matched)!=1:raise ValueError('Ambiguous demand group')
   parts=pages('/entity/demand/'+d['id']+'/positions',{});qty=sum(p['quantity']for p in parts if p.get('assortment',{}).get('meta',{}).get('href')==href)
   if qty:docs.append(dict(id=d['id'],name=d['name'],group=next(iter(matched)),quantity=qty,applicable=d['applicable'],store_id=STORE,updated=d['updated']))
  return dict(observed_at=stamp(),documents=docs,header_count=len(headers),exact_product_id=prods[0]['id'])
 try:
  stage('msk',lambda:reader.stock(['143-ReginaBag-black'],'msk'))
  for i in range(3):
   stage('stock:'+str(i),lambda i=i:dict(observed_at=stamp(),raw=wb(i,'/api/v3/stocks/'+str(WAREHOUSES[i]),{'chrtIds':[SIZES[i]]})))
   stage('orders:'+str(i),lambda i=i:wborders(i))
  stage('stock:3',lambda:dict(observed_at=stamp(),raw=oz('/v2/product/info/stocks-by-warehouse/fbs',{'offer_id':['143-ReginaBag-black'],'limit':1000,'cursor':''})))
  stage('orders:3',ozorders)
  if all('orders:'+str(i)in result['inputs']for i in range(4)):stage('ms_demands',documents)
 finally:requests.sessions.Session.request=original
 result.update(status='complete'if not result['errors']else'partial',completed_at=stamp());save();print(json.dumps(dict(status=result['status'],errors=result['errors'],wb_writes=0)))
if __name__=='__main__':run()

