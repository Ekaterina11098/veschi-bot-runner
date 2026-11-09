"""Owner-requested single-SKU MS document audit. All business HTTP is GET only."""
import os,json,time
from datetime import datetime,timezone,timedelta
from urllib.parse import urlparse
import requests
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest

ART='38-furmanizhka-white'
ROOT='technical:owner-38-reserve-audit:2026-11-09'
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
    if datetime.now(timezone(timedelta(hours=3))).date().isoformat()!='2026-11-09':raise ReadError('Audit date closed')
    result=dict(article=ART,started=time.time(),business_writes=0,documents={},errors={})
    def save():
        with runtime_db() as db:
            s=Store(db,postgres=True)
            with s.transaction():s.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',(ROOT,canonical(result),'{}',digest({}),'technical-no-executor',time.time()))
    products=[p for p in rows('/entity/product',search='38') if str(p.get('article','')).casefold()==ART]
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
    for kind in ('demand','move','salesreturn','customerorder'):
        try:
            datefilter='moment>=2026-10-01 00:00:00;moment<2026-11-10 00:00:00'
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
    wb_audit(result)
    result['complete']=not result['errors'];result['received_at']=time.time();save();seal('article143-ms-audit',result)
    print(json.dumps({'complete':result['complete'],'document_counts':{k:len(v) for k,v in result['documents'].items()},'errors':result['errors'],'business_writes':0}))

def wb_audit(result):
    import tg_agent_new as g
    from stock_shared_requests import SharedRequests
    from stock_wb_supply_history import complete_wb_supply_history
    from stock_execution_fence import cloud_writer
    with runtime_db() as lock:
      with cloud_writer(lock):
       with runtime_db() as db:
        store=Store(db,postgres=True);shared=SharedRequests(store)
        g.STOCK_REQUEST_GATE=shared;g.STOCK_SHARED_ORDERS=shared
        g._CACHE_GET=lambda k:None;g._CACHE_SET=lambda *a:None
        g.check_run_budget=lambda:None
        row=store.sql('SELECT snapshot FROM stock_runs WHERE id=?',('technical:stock-daily:2026-11-09:owner-four-reserve-correction',)).fetchone()
        source=json.loads(row[0])['source'];units=[u for u in source['unposted_orders']['units'] if u['article']==ART]
        token=g.cabinet_tokens()[2]
        status=g.api('POST',g.WB_MARKET+'/api/v3/orders/status',token,json={'orders':[int(u['id']) for u in units]})
        result['current_statuses']=status
        physical,unresolved=g.load_ms_stocks_dict()
        result['live_moscow']=physical.get(ART)
        result['ms_read_status']=getattr(g,'MS_STOCK_STATUS',{})
        result['original_units']=units;result['supply_proof']=[];result['supply_units']=[]
        def checkpoint():
            with store.transaction():store.sql('UPDATE stock_runs SET snapshot=? WHERE id=?',(canonical(result),ROOT))
        checkpoint()
        all_units=source['unposted_orders']['units']
        for group in sorted({u['group'] for u in units}):
            supply=group[3:]
            ids=g.api('GET',g.WB_MARKET+'/api/marketplace/v3/supplies/'+supply+'/order-ids',token,retry_read_network=True)['orderIds']
            info=g.api('GET',g.WB_MARKET+'/api/v3/supplies/'+supply,token,retry_read_network=True)
            result.setdefault('membership',[]).append(dict(supply=supply,ids=ids,info=info,removed=[u['id'] for u in units if u['group']==group and int(u['id']) not in ids]))
            checkpoint()
            members=[u for u in all_units if u['group']==group and int(u['id']) in ids]
            if not ids:continue
            if not members:
                result['errors'][supply]='No retained anchor for nonempty supply';checkpoint();continue
            try:
                complete,proof=complete_wb_supply_history(g,members,[dict(group=group)])
                result['supply_proof']+=proof
                result['supply_units'] += [u for u in complete if u['article']==ART]
            except Exception as exc:result['errors'][supply]=str(exc)
            checkpoint()
if __name__=='__main__':main()


