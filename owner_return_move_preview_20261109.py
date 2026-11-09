"""Owner-requested single-SKU MS document audit. All business HTTP is GET only."""
import os,json,time
from datetime import datetime,timezone,timedelta
from urllib.parse import urlparse
import requests
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest

ART='143-reginabag-black'
ROOT='technical:owner-143-ms-audit:2026-11-04'
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
    result=dict(started=time.time(),business_writes=0,wb_calls=0,documents=[])
    stores=rows('/entity/store');names={href(s):s['name'] for s in stores}
    msk=[s for s in stores if s['name']=='МСК']
    assert len(msk)==1
    target=href(msk[0])
    docs=rows('/entity/move',filter='moment>=2026-11-02 00:00:00',expand='positions.assortment')
    totals={}
    for d in docs:
        source=names.get(href(d.get('sourceStore')),'')
        if href(d.get('targetStore'))!=target or not d.get('applicable') or not ('фбо' in source.casefold() or 'fbo' in source.casefold()):continue
        ps=d.get('positions',{});parts=ps.get('rows',[])
        if len(parts)!=ps.get('meta',{}).get('size'):parts=rows(href(ps),expand='assortment')
        pos=[]
        for p in parts:
            art=str(p.get('assortment',{}).get('article','')).strip().casefold()
            q=p['quantity']
            pos.append(dict(article=art,quantity=q))
            if art:totals[art]=totals.get(art,0)+q
        result['documents'].append(dict(id=d['id'],name=d['name'],moment=d['moment'],updated=d['updated'],source=source,positions=pos))
    with runtime_db() as db:
        s=Store(db,postgres=True)
        snap=json.loads(s.sql('SELECT snapshot FROM stock_runs WHERE id=?',('technical:stock-daily:2026-11-09:0700',)).fetchone()[0])
    result['basis']='Saved Nov9 morning plan; indicative only, not a future20:00 execution plan'
    result['source_observed_at']=snap['source']['started']
    result['candidates']=[]
    for m in snap['full_plan'].get('manual',[]):
        a=m['article'];ret=totals.get(a,0)
        if not ret:continue
        china=m['after_automatic'][2]
        if china is None:continue
        head=max(0,m['available_moscow']-sum(x or 0 for x in m['after_automatic']))
        add=min(ret,head)
        result['candidates'].append(dict(article=a,returned=ret,moscow=m['moscow'],pending=m['pending_unposted'],available=m['available_moscow'],china_before=china,add=add,china_after=china+add))
    result['complete']=True
    with runtime_db() as db:
        s=Store(db,postgres=True)
        with s.transaction():s.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',('technical:owner-return-move-preview:2026-11-09',canonical(result),'{}',digest({}),'technical-no-executor',time.time()))
    print(json.dumps(dict(complete=True,documents=len(result['documents']),candidates=result['candidates'],business_writes=0,wb_calls=0),ensure_ascii=False))
if __name__=='__main__':main()
