"""Read-only physical-pool and exact WB location evidence; no publication or Telegram."""
import json,time
import tg_agent_new as g
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest,Stopped
from stock_shared_requests import SharedRequests
from stock_execution_fence import cloud_writer
from stock_china_mgt import read_store,qty
from stock_china_mgt_publish import ARTICLES
ROOT='technical:china-mgt-routing-audit:2026-11-11'
with runtime_db() as lock:
 with cloud_writer(lock):
  with runtime_db() as db:
   store=Store(db,postgres=True);shared=SharedRequests(store)
   g.STOCK_REQUEST_GATE=shared;g.STOCK_SHARED_ORDERS=shared;g.check_run_budget=lambda:None
   g._CACHE_GET=lambda k:None;g._CACHE_SET=lambda *a:None
   g.MS_STORE_NAME='МСК';msk,unknown=g.load_ms_stocks_dict();msk_at=time.time()
   china,unresolved,china_at=read_store(g)
   found={a:dict(article=a,msk=msk.get(a),china=china.get(a),wb=[]) for a in ARTICLES}
   for i,t in enumerate(g.cabinet_tokens()):
    cards=g.get_real_wb_cards_and_scores(t);sizes=g.article_size_ids(cards)
    for wh in ([1863255] if i==0 else [854652] if i==1 else [2126188,2308581]):
     ids=sorted({v for a,values in sizes.items() if a in ARTICLES for v in values});amounts={}
     if ids:
      rows=g.api('POST',g.WB_MARKET+'/api/v3/stocks/'+str(wh),t,json={'chrtIds':ids},retry_read_network=True).get('stocks')
      if not isinstance(rows,list):raise Stopped('WB stock rows missing')
      for row in rows:
       if row.get('chrtId') not in ids or row['chrtId'] in amounts:raise Stopped('WB stock identity mismatch')
       amounts[row['chrtId']]=qty(row.get('amount'))
     for a in ARTICLES:
      values=sizes.get(a,set())
      found[a]['wb'].append(dict(cabinet=i,warehouse=wh,card_present=bool(values),size_ids=sorted(values),quantity=sum(amounts[v] for v in values) if values and values.issubset(amounts) else None,missing_quantity_ids=sorted(values-set(amounts))))
   result=dict(complete=True,read_only=True,stock_writes=0,ms_document_writes=0,telegram_messages=0,msk_observed_at=msk_at,china_observed_at=china_at,rows=list(found.values()),unresolved_positive_china=unresolved,finished_at=time.time())
   with store.transaction():store.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',(ROOT,canonical(result),'{}',digest({}),'technical-no-executor',time.time()))
   seal('mgt-pool-routing-audit',result);print(json.dumps(dict(complete=True,stock_writes=0,articles=len(found))))

