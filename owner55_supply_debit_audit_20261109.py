"""Exact55order IDs versus retained WB supplies and posted MSK headers; read only."""
import json,time
from datetime import datetime,timezone,timedelta
import tg_agent_new as g
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest,Stopped
from stock_execution_fence import cloud_writer
from stock_shared_requests import SharedRequests
from stock_unposted_source import ms_headers,ms_rows,document_identities,uid,demand_positions,href
ROOT='technical:owner55-supply-debit-audit:2026-11-09'
with runtime_db() as lock:
 with cloud_writer(lock):
  with runtime_db() as db:
   s=Store(db,postgres=True);shared=SharedRequests(s)
   g.STOCK_REQUEST_GATE=shared;g.STOCK_SHARED_ORDERS=shared
   g._CACHE_GET=lambda k:None;g._CACHE_SET=lambda *a:None;g.check_run_budget=lambda:None
   prior=json.loads(s.sql('SELECT snapshot FROM stock_runs WHERE id=?',('technical:owner-cancel57-audit:2026-11-09',)).fetchone()[0])
   targets=[u for u in prior['candidates'] if u['id'] not in ('6155723784','6209276833')]
   if len(targets)!=55:raise Stopped('Expected exact55orders')
   first=min(datetime.fromisoformat(u['created_at'].replace('Z','+00:00')) for u in targets)-timedelta(days=1)
   since=first.astimezone(timezone(timedelta(hours=3))).strftime('%Y-%m-%d %H:%M:%S')
   headers,store_id,manifest=ms_headers(g,since)
   orders={r['id']:r for r in ms_rows(g,g.MS_API+'/entity/customerorder',filter='moment>='+since)}
   docs=[]
   for row in headers:
    ref=row.get('customerOrder') or {};order=orders.get(uid(ref),{})
    if ref and not order:order=g.api('GET',ref['meta']['href'],g.MS_TOKEN,wb=False)
    supplies,posts=document_identities(row,order)
    docs.append(dict(id=row['id'],name=row.get('name'),supplies=sorted(supplies),
      externalCode=row.get('externalCode'),agent_id=uid(row.get('agent')),moment=row.get('moment'),
      applicable=row.get('applicable'),store_id=uid(row.get('store')),updated=row.get('updated')))
   result=dict(complete=False,started=time.time(),business_writes=0,runtime_ledger_writes=0,
    targets=targets,since=since,posted_msk_documents=docs,cabinets={},matches=[],errors=[],unresolved_ms_groups=[])
   def save():
    with s.transaction():s.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',
     (ROOT,canonical(result),'{}',digest({}),'technical-no-executor',time.time()))
   save()
   all_known=set()
   for cab in sorted({u['cabinet'] for u in targets}):
    token=g.cabinet_tokens()[cab];target_ids={int(u['id']) for u in targets if u['cabinet']==cab}
    seen=set();cursor=0;supplies={}
    for _ in range(100):
     if cursor in seen:raise Stopped('WB supply inventory cursor repeated')
     seen.add(cursor)
     response=g.api('GET',g.WB_MARKET+'/api/v3/supplies',token,params=dict(limit=1000,next=cursor),retry_read_network=True)
     rows=response.get('supplies')
     if not isinstance(rows,list) or type(response.get('next')) is not int:raise Stopped('WB supply inventory incomplete')
     for row in rows:
      sid=row.get('id')
      if not isinstance(sid,str) or not sid:raise Stopped('WB supply identity missing')
      if sid in supplies and supplies[sid]!=row:raise Stopped('WB supply inventory changed')
      supplies[sid]=row
     if not rows or not response['next']:break
     cursor=response['next']
    else:raise Stopped('WB supply inventory bound exceeded')
    all_known.update(supplies)
    needed={sid for doc in docs for sid in doc['supplies'] if sid in supplies}
    # All newer/unclosed supplies are checked too, even without an MS demand.
    for sid,row in supplies.items():
     closed=row.get('closedAt')
     if not closed or datetime.fromisoformat(closed.replace('Z','+00:00'))>=first:needed.add(sid)
    entry=dict(retained_supplies=len(supplies),checked=[],matches=[])
    result['cabinets'][str(cab)]=entry;save()
    for sid in sorted(needed):
     response=g.api('GET',g.WB_MARKET+'/api/marketplace/v3/supplies/'+sid+'/order-ids',token,retry_read_network=True)
     ids=response.get('orderIds')
     if not isinstance(ids,list) or any(type(i) is not int for i in ids) or len(ids)!=len(set(ids)):raise Stopped('WB supply membership coverage invalid')
     found=sorted(target_ids&set(ids))
     entry['checked'].append(dict(supply_id=sid,order_count=len(ids),order_ids_digest=digest(sorted(ids)),target_ids=found))
     if found:
      match=dict(cabinet=cab,supply=supplies[sid],order_ids=ids,target_ids=found,
         ms_documents=[d for d in docs if sid in d['supplies']])
      result['matches'].append(match);entry['matches'].append(sid)
     if len(entry['checked'])%10==0:save()
    save()
   result['unresolved_ms_groups']=sorted({sid for d in docs for sid in d['supplies'] if sid not in all_known})
   # Record exact matched MS positions only; no article-only inferred debit.
   matching_ids={d['id'] for m in result['matches'] for d in m['ms_documents']}
   if matching_ids:
    parts=demand_positions(g,[h for h in headers if h['id'] in matching_ids])
    products={href(p):p for p in g.ms_rows(g.MS_API+'/entity/assortment',filter='archived=false;archived=true')}
    for m in result['matches']:
     for d in m['ms_documents']:
      d['positions']=[dict(article=g.norm(products.get(href(p.get('assortment')),p.get('assortment',{})).get('article')),
                           quantity=p.get('quantity')) for p in parts[d['id']]]
   _,store2,after=ms_headers(g,since)
   if store2!=store_id or after!=manifest:raise Stopped('MS demands changed during exact55supply audit')
   result['complete']=True;result['received_at']=time.time();save();seal('owner55-supply-debit-audit',result)
   print(json.dumps(dict(complete=True,targets=len(targets),supplies_checked=sum(len(v['checked']) for v in result['cabinets'].values()),
       matched_order_ids=sorted({i for m in result['matches'] for i in m['target_ids']}),business_writes=0)))
