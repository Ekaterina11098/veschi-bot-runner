"""Exact owner-authorized reconciliation and fresh calculation for one article.
No document writes, no MGT writes, no Telegram delivery, no old PUT replay.
"""
import copy,json,os,time
from stock_operation_store import Store,Stopped,canonical,digest
from stock_execution_fence import cloud_writer,require_cloud_lease,EXPLICIT_HOLDS

ARTICLE='2-furpanama-black'
OLD='cloud:5931c3a5-2d36-4080-83bb-71eb05483c84'
ROOT='technical:stock-daily:2026-11-14:owner-furpanama-recovery'
AUTH='owner-fresh-reconcile-replan-2-furpanama-black-20261114'
OLD_BODY={'before':60,'target':63,'cabinet':2,'location':{'chrtId':2381216373,'warehouse':2126188}}

def filtered(source):
    result=copy.deepcopy(source)
    for key in ('moscow_raw','inventory_raw'):
        if key in result:result[key]={a:q for a,q in result[key].items() if a==ARTICLE}
    result['fbs']=[{a:q for a,q in row.items() if a==ARTICLE} for row in result['fbs']]
    if result.get('unposted_orders'):
        result['unposted_orders']['available_moscow']={a:q for a,q in result['unposted_orders']['available_moscow'].items() if a==ARTICLE}
    return result

def validate_plan(plan):
    for section in ('articles','manual','blocked'):
        if any(m['article']!=ARTICLE for m in plan.get(section,[])):raise Stopped('Owner recovery escaped one-article scope')
    for member in plan.get('articles',[]):
        for op in member['operations']:
            loc=member['locations'][op['cabinet']]
            if op['cabinet']!=2 or loc!={'warehouse':2126188,'chrtId':2381216373}:raise Stopped('Only exact China MSK position may change')
    if plan.get('blocked'):raise Stopped('Fresh evidence still blocks article: '+canonical(plan['blocked']))

def retire_old(store,g,data,persist):
    require_cloud_lease()
    if data.get('old_reconciled'):return
    snapshot,plan,approved,origin,created=store.run(OLD)
    ops=store.operations(OLD)
    if origin!='cloud' or snapshot['article']!=ARTICLE or len(ops)!=1 or ops[0][0]!=0 or ops[0][1]!=OLD_BODY:
        raise Stopped('Old uncertain plan differs from inspected exact operation')
    if ops[0][2] not in ('uncertain','sent'):raise Stopped('Old operation state changed; inspect before continuing')
    claim=store.sql("SELECT id,detail FROM stock_events WHERE run=? AND seq=0 AND state='dispatch_claimed'",(OLD,)).fetchall()
    if len(claim)!=1:raise Stopped('Original dispatch claim must remain exactly one')
    from stock_batch_transport import SavedBatchAdapter
    actual=SavedBatchAdapter(g,store,OLD,{}).read(OLD_BODY)
    state=ops[0][2];new='confirmed' if actual==63 else 'invalidated'
    record={'authorization':AUTH,'previous_state':state,'result':new,'actual':actual,'observed_at':time.time(),
            'original_body_digest':digest(OLD_BODY),'original_dispatch_claim':list(claim[0]),
            'reason':'Fresh exact readback; explicitly supersede old intent before independent fresh owner plan',
            'no_assertion_of_non_execution':True,'original_claim_preserved':True}
    with store.transaction():
        lock=store.sql('SELECT owner_run FROM stock_sku_locks WHERE article=?',(ARTICLE,)).fetchone()
        if lock!=(OLD,):raise Stopped('Article lock ownership changed')
        if store.sql('UPDATE stock_operations SET state=? WHERE run=? AND seq=0 AND state=?',(new,OLD,state)).rowcount!=1:raise Stopped('Concurrent old state change')
        store.event(OLD,0,new,record)
        store.sql('DELETE FROM stock_sku_locks WHERE article=? AND owner_run=?',(ARTICLE,OLD))
        data['old_reconciled']=record
        data['source']['fbs'][2][ARTICLE]=actual
        persist(transaction=False)

def main(factory):
    import tg_agent_new as g,auto_stock as a
    import stock_regular_service as service
    from stock_approved_warehouses import install
    from stock_shared_requests import SharedRequests
    from stock_storage_health import verify_runtime_storage
    from stock_live_capacity import LiveCapacity,fresh
    from stock_prepare_members import prepare_members
    from stock_group_execution import execute_groups
    from stock_order_demand import speed
    from stock_china_mgt import policy
    p=policy()
    if p.get('publication_enabled') is not False or p.get('mode')!='owner_paused':raise Stopped('Guangzhou pause must stay active')
    install(g);a.check_write_credentials();g.STOCK_FURCOAT_ENABLED=True
    with cloud_writer(factory()):
      with factory() as db:
        store=Store(db,postgres=True)
        row=store.sql('SELECT snapshot FROM stock_runs WHERE id=?',(ROOT,)).fetchone();db.commit()
        data=json.loads(row[0]) if row else {'authorization':AUTH,'started_at':time.time(),'generation':0,'registry':{},'status':'collecting','execution_complete':False,'cache':{}}
        if data.get('authorization')!=AUTH:raise Stopped('Owner root authorization differs')
        if data.get('execution_complete'):return data
        def persist(transaction=True):
            def write():store.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot,plan=excluded.plan,digest=excluded.digest',
                (ROOT,canonical(data),canonical(data.get('plan',{})),digest(data.get('plan',{})),'owner-authorized-recovery',data['started_at']))
            if transaction:
                with store.transaction():write()
            else:write()
        persist()
        g.RUN_DEADLINE=time.monotonic()+2400
        shared=SharedRequests(store,budget=lambda:g.check_run_budget())
        g.STOCK_SHARED_ORDERS=shared;g.STOCK_REQUEST_GATE=shared
        g._CACHE_GET=lambda key:shared.get(key)
        g._CACHE_SET=lambda key,value,ttl:shared.put(key,value,ttl)
        os.environ['STOCK_STORAGE_PROOF_FILE']=os.path.join(os.environ['RUNNER_TEMP'],'furpanama-storage-proof.json')
        os.environ['STOCK_STORAGE_PROOF_SCOPE']=ROOT
        def verify():
            probe={'scope':ROOT,'nonce':os.urandom(16).hex()}
            def write(v):data['storage_probe']=v;persist()
            def read():
                row=store.sql('SELECT snapshot FROM stock_runs WHERE id=?',(ROOT,)).fetchone();db.commit();return json.loads(row[0])['storage_probe']
            verify_runtime_storage(write,read,probe)
        verify()
        try:
            scope=ROOT+':generation:0'
            for rid,raw in store.sql("SELECT id,snapshot FROM stock_runs WHERE origin='cloud'").fetchall():
                snap=json.loads(raw)
                if snap.get('batch_scope')==scope:
                    if snap.get('article')!=ARTICLE:raise Stopped('Unexpected member in owner scope')
                    data['registry'][ARTICLE]=rid
            db.commit()
            if not data.get('source'):
                orders=[speed(g,t,g.SALES_DAYS) for t in g.cabinet_tokens()]
                if not all(g.SALES_STATUS.get(t,{}).get('available',False) for t in g.cabinet_tokens()):raise Stopped('Complete 7-day demand required')
                data['source']=filtered(service.capture(g,{ARTICLE},orders));data['status']='source_collected';persist()
            if service.source_expired(data['source']):raise Stopped('Owner source expired; fresh scoped continuation required')
            if not data.get('old_reconciled'):retire_old(store,g,data,persist)
            if not data.get('plan'):
                blocked=set(EXPLICIT_HOLDS)|{art for art,rid in store.sql('SELECT article,owner_run FROM stock_sku_locks').fetchall() if rid not in data['registry'].values()};db.commit()
                data['plan']=service.plan_source(g,a,data['source'],blocked,set());validate_plan(data['plan'])
                data['status']='planned';persist()
            validate_plan(data['plan'])
            prepare_members(store,g,data['plan'],data['source'],data['source']['started'],service.restored_cards(data['source']),scope,data['registry'],scope=scope)
            data['status']='executing';persist()
            live=LiveCapacity(g,lambda:data['source'])
            def capacity(group_store,items):
                verify();proof=live.guard(group_store,items)
                with store.transaction():store.event(ROOT,None,'capacity_verified',{'orders_observed_at':proof['observed_at'],'physical_observed_at':proof['physical_observed_at'],'digest':proof['digest']})
                if not fresh(proof):raise Stopped('Capacity expired before dispatch')
            g.STOCK_CAPACITY_BEFORE_DISPATCH=capacity
            def progress():
                data['states']={rid:[{'seq':s,'state':state,'body':body} for s,body,state,_ in store.operations(rid)] for rid in data['registry'].values()};persist()
            held=execute_groups(store,g,data['registry'],{m['article']:m for m in data['plan']['articles']},progress)
            if held:raise Stopped('Fresh operation uncertain; readback only, no blind retry')
            # Final exact live stock check, separate from per-operation confirmation.
            before=data['source']['fbs'][2].get(ARTICLE)
            target=next((m['target'][2] for m in data['plan']['articles'] if m['article']==ARTICLE),before)
            from stock_group_execution import values_from_response
            values=values_from_response(g.api('POST',g.WB_MARKET+'/api/v3/stocks/2126188',g.cabinet_tokens()[2],json={'chrtIds':[2381216373]},retry_read_network=True))
            actual=values.get(2381216373)
            if actual!=target:raise Stopped('Final actual differs from fresh target; no blind resend')
            if store.sql('SELECT owner_run FROM stock_sku_locks WHERE article=?',(ARTICLE,)).fetchone():raise Stopped('Article remains locked')
            original=store.operations(OLD)
            if original[0][1]!=OLD_BODY or store.sql("SELECT count(*) FROM stock_events WHERE run=? AND seq=0 AND state='dispatch_claimed'",(OLD,)).fetchone()[0]!=1:raise Stopped('Old body or claim changed')
            data.update(execution_complete=True,status='complete',completed_at=time.time(),before=before,target=target,actual=actual,
                        telegram_delivery='not_requested',guangzhou_publication='owner_paused')
            persist();return data
        except Exception as exc:
            data.update(status='stopped',last_error=str(exc),last_error_type=type(exc).__name__,stopped_at=time.time());persist();raise

if __name__=='__main__':
    from stock_deploy_support import runtime_db,seal,error
    try:
        result=main(runtime_db);seal('owner-furpanama-recovery',result)
        print(json.dumps({k:result.get(k) for k in ('status','execution_complete','before','target','actual','guangzhou_publication')}))
    except Exception as exc:
        seal('owner-furpanama-recovery-error',error(exc));print(json.dumps({'status':'stopped','error_type':type(exc).__name__,'message':str(exc)}));raise