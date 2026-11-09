"""Repair current-order ledger through normal complete read-only reconciliation."""
import json,time
import tg_agent_new as g
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest
from stock_shared_requests import SharedRequests
from stock_execution_fence import cloud_writer
from stock_approved_warehouses import install
from stock_unposted_source import collect
ROOT='technical:owner-debit2-reserve-repair:2026-11-09'
with runtime_db() as lock:
 with cloud_writer(lock):
  with runtime_db() as db:
   s=Store(db,postgres=True)
   done=s.sql('SELECT snapshot FROM stock_runs WHERE id=?',(ROOT,)).fetchone()
   if done and json.loads(done[0]).get('complete'):print('Already reconciled; no business calls')
   else:
    source=json.loads(s.sql('SELECT snapshot FROM stock_runs WHERE id=?',('technical:stock-daily:2026-11-09:owner-four-reserve-correction',)).fetchone()[0])['source']
    shared=SharedRequests(s)
    g.STOCK_REQUEST_GATE=shared;g.STOCK_SHARED_ORDERS=shared
    g._CACHE_GET=lambda k:None;g._CACHE_SET=lambda *a:None
    g.check_run_budget=lambda:None
    install(g)
    # Capture the exact57 raw order identities during the normal complete
    # read; reuse these for cancellation timestamp evidence without new polling.
    audit=json.loads(s.sql('SELECT snapshot FROM stock_runs WHERE id=?',('technical:owner-cancel57-audit:2026-11-09',)).fetchone()[0])
    wanted={(u['cabinet'],str(u['id'])) for u in audit['candidates']}
    raw57={};status57={};original_api=g.api
    def observed(method,url,token,*args,**kwargs):
     data=original_api(method,url,token,*args,**kwargs)
     if url.startswith(g.WB_MARKET+'/api/v3/orders'):
      cab=g.cabinet_tokens().index(token)
      for row in data.get('orders',[]) if isinstance(data,dict) else []:
       if (cab,str(row.get('id'))) in wanted:
        key=str(cab)+':'+str(row['id'])
        if 'supplierStatus' in row:status57[key]=row
        elif 'article' in row:
         raw57[key]={k:row.get(k) for k in ('id','article','supplyId','createdAt','rid','orderUid','warehouseId','deliveryType','crossBorderType','isZeroOrder')}
     return data
    g.api=observed
    result=collect(g,source)
    articles=('529-noelbag-lpink','534-noelbag-emerald')
    receipt=dict(complete=True,at=time.time(),business_writes=0,
      articles={art:dict(physical=result['physical_moscow'].get(art),pending=result['pending'].get(art,0),
       free=result['available_moscow'].get(art),blocked=result['blocked'].get(art),
       evidence=[r for r in result['current_debit_evidence'] if r['article']==art]) for art in articles},
      raw57=raw57,status57=status57,source_observed_at=result['observed_at'],
      historical_debit_coverage_v1=result['ledger_candidate'].get('historical_debit_coverage_v1'),
      pending=result['pending'],documents=result['documents'])
    with s.transaction():
     s.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',
      (ROOT,canonical(receipt),'{}',digest({}),'technical-no-executor',time.time()))
    seal('owner-debit2-reserve-repair',receipt)
    print(json.dumps(receipt))
