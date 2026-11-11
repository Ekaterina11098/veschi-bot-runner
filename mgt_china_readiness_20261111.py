"""Read-only readiness for new MS China stock pool and WB2308581."""
import json,time,math
import tg_agent_new as g
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest,Stopped
from stock_shared_requests import SharedRequests
from stock_execution_fence import cloud_writer
ROOT='technical:mgt-china-readiness:2026-11-11'
with runtime_db() as lock:
 with cloud_writer(lock):
  with runtime_db() as db:
   store=Store(db,postgres=True);shared=SharedRequests(store)
   g.STOCK_REQUEST_GATE=shared;g.STOCK_SHARED_ORDERS=shared;g.check_run_budget=lambda:None
   g._CACHE_GET=lambda k:None;g._CACHE_SET=lambda *a:None
   stores=g.ms_rows(g.MS_API+'/entity/store')
   matches=[s for s in stores if str(s.get('name','')).strip()=='Склад в Китае']
   if len(matches)!=1:raise Stopped('Exact new MS store name not unique')
   msstore=matches[0];g.MS_STORE_NAME=msstore['name']
   physical,unresolved=g.load_ms_stocks_dict()
   whs=g.api('GET',g.WB_MARKET+'/api/v3/warehouses',g.cabinet_tokens()[2],retry_read_network=True)
   if not isinstance(whs,list):raise Stopped('WB warehouse list unknown')
   selected=[w for w in whs if w.get('id')==2308581]
   if len(selected)!=1:raise Stopped('Owner WB warehouse2308581 unavailable in China account')
   cards=g.get_real_wb_cards_and_scores(g.cabinet_tokens()[2]);sizes=g.article_size_ids(cards)
   ids=sorted({v for values in sizes.values() for v in values});amounts={}
   for offset in range(0,len(ids),1000):
    page=ids[offset:offset+1000]
    rows=g.api('POST',g.WB_MARKET+'/api/v3/stocks/2308581',g.cabinet_tokens()[2],json={'chrtIds':page},retry_read_network=True).get('stocks')
    if not isinstance(rows,list):raise Stopped('MGT FBS stock rows unknown')
    for r in rows:
     ident=r.get('chrtId');q=r.get('amount')
     if ident not in page or ident in amounts or type(q) not in(int,float) or not math.isfinite(q) or q<0 or int(q)!=q:raise Stopped('MGT stock coverage invalid')
     amounts[ident]=int(q)
   if set(amounts)!=set(ids):raise Stopped('MGT stock response incomplete')
   rows=[]
   allarts=set(a for a,q in physical.items() if q!=0)|{a for a,vals in sizes.items() if sum(amounts[v] for v in vals)>0}
   for art in sorted(allarts):
    matching=[c for c in cards if g.norm(c.get('vendorCode'))==art];values=sizes.get(art,set())
    rows.append(dict(article=art,physical=physical.get(art),fbs=sum(amounts[v] for v in values) if values else None,
     card_count=len(matching),sizes=sorted(values),photo=all(bool(c.get('photos')) for c in matching) if matching else False))
   result=dict(complete=True,readiness_only=True,stock_writes=0,ms_document_writes=0,started_at=time.time(),finished_at=time.time(),ms_store={k:msstore.get(k) for k in('id','name','archived')},wb_warehouse=selected[0],rows=rows,unresolved_ms=unresolved,wb_catalog_cards=len(cards))
   with store.transaction():store.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',(ROOT,canonical(result),'{}',digest({}),'technical-no-executor',time.time()))
   seal('mgt-china-readiness',result);print(json.dumps(dict(complete=True,stock_writes=0)))
