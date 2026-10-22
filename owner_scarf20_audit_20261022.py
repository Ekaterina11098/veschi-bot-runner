"""Owner-requested single-SKU MS document audit. All business HTTP is GET only."""
import os,json,time
from datetime import datetime,timezone,timedelta
from urllib.parse import urlparse
import requests
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest

ART='20-furbigscarf-khaki'
ROOT='technical:owner-scarf20-ms-audit:2026-10-22'
BASE='https://api.moysklad.ru/api/remap/1.2'
class ReadError(RuntimeError):pass
def get(path,**params):
    url=path if path.startswith('https://') else BASE+path
    if urlparse(url).netloc!='api.moysklad.ru' or not urlparse(url).path.startswith('/api/remap/1.2/'):raise ReadError('Unexpected source URL')
    r=requests.get(url,headers={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN'],'Accept-Encoding':'gzip'},params=params,timeout=(5,40))
    if r.status_code!=200:raise ReadError('MS read HTTP '+str(r.status_code)+' '+urlparse(url).path)
    return r.json()
def rows(path,**params):
    out=[];expected=None
    for offset in range(0,5000,100):
        data=get(path,**dict(params,limit=100,offset=offset));page=data.get('rows');size=data.get('meta',{}).get('size')
        if not isinstance(page,list) or type(size) is not int:raise ReadError('Incomplete MS rows')
        if expected is not None and size!=expected:raise ReadError('MS collection changed during audit')
        expected=size;out+=page
        if len(page)<100:
            if len(out)!=size:raise ReadError('Incomplete MS collection')
            return out
    raise ReadError('Bounded audit exceeded5000 rows')
def href(value):return (value or {}).get('meta',{}).get('href','')
def main():
    if datetime.now(timezone(timedelta(hours=3))).date().isoformat()!='2026-10-22':raise ReadError('Audit date closed')
    result=dict(article=ART,started=time.time(),business_writes=0,documents={},errors={})
    def save():
        with runtime_db() as db:
            s=Store(db,postgres=True)
            with s.transaction():s.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',(ROOT,canonical(result),'{}',digest({}),'technical-no-executor',time.time()))
    products=[p for p in rows('/entity/product',filter='article=20-FurBigScarf-khaki') if str(p.get('article','')).casefold()==ART]
    if len(products)!=1:raise ReadError('Exact product match is ambiguous or missing')
    product=products[0];product_url=href(product);pid=product['id']
    stores=[s for s in rows('/entity/store') if s.get('name')=='МСК']
    if len(stores)!=1:raise ReadError('MSK store is ambiguous')
    store=stores[0];store_url=href(store)
    result['product']={k:product.get(k) for k in ('id','article','name')};result['store']={k:store.get(k) for k in ('id','name')};save()
    try:
        stock=rows('/report/stock/bystore',filter='store='+store_url+';stockMode=all')
        result['current_stock']=[r for r in stock if href(r.get('assortment') or r).endswith('/'+pid)]
    except ReadError as exc:result['errors']['stock']=str(exc)
    save()
    for kind in ('demand','move','loss','enter','supply','salesreturn','purchasereturn','retaildemand','retailsalesreturn','customerorder'):
        try:
            datefilter='moment>=2026-10-14 00:00:00;moment<2026-10-23 00:00:00'
            try:docs=rows('/entity/'+kind,filter=datefilter+';assortment='+product_url,expand='positions.assortment')
            except ReadError as exc:
                if 'HTTP 400 ' not in str(exc):raise
                docs=rows('/entity/'+kind,filter=datefilter,expand='positions.assortment')
            matched=[]
            for doc in docs:
                positions=doc.get('positions',{});parts=positions.get('rows')
                if not isinstance(parts,list) or len(parts)!=positions.get('meta',{}).get('size'):
                    parts=rows(href(positions))
                selected=[p for p in parts if href(p.get('assortment')).endswith('/'+pid)]
                if not selected:continue
                keep={k:doc.get(k) for k in ('id','name','moment','created','updated','applicable','description','externalCode')}
                keep['stores']={k:href(doc.get(k)) for k in ('store','sourceStore','targetStore') if doc.get(k)}
                keep['positions']=[{k:p.get(k) for k in ('quantity','reserve','shipped')} for p in selected]
                keep['customerOrder']=href(doc.get('customerOrder'));matched.append(keep)
            result['documents'][kind]=matched
        except ReadError as exc:result['errors'][kind]=str(exc)
        save()
    result['complete']=not result['errors'];result['received_at']=time.time();save();seal('scarf20-ms-audit',result)
    print(json.dumps({'complete':result['complete'],'document_counts':{k:len(v) for k,v in result['documents'].items()},'errors':result['errors'],'business_writes':0}))
if __name__=='__main__':main()

