"""Only immutable Telegram approvals after the configured cutover; no old queues."""
import os,sys,json,time,hmac,hashlib,base64,contextlib,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))

def due_intents(repo,cfg,cabinet=None,now=None):
    if cabinet not in (None,'token_1','token_2','token_3'):raise ValueError('Unknown worker cabinet')
    now=time.time() if now is None else now
    rows=repo.execute('SELECT id,payload FROM {p}intents').fetchall()
    groups={c:[] for c in ('token_1','token_2','token_3')}
    for intent_id,raw in rows:
        i=json.loads(raw)
        if (i.get('cabinet') not in groups or (cabinet is not None and i.get('cabinet')!=cabinet) or
            max(i.get('retry_at') or 0,i.get('worker_retry_at') or 0)>now or i.get('status') not in ('awaiting_preflight','verify') or
            i.get('created_at',0)<cfg['cutover'] or str(i.get('owner_id'))!=str(cfg['owner_id']) or str(i.get('chat_id')) not in {str(cfg['chat_id']),str(cfg.get('content_group_chat_id',''))}):continue
        groups[i['cabinet']].append(i)
    # Finish a cabinet's current write/readback before consuming its GET quota on another review.
    return [sorted(rows,key=lambda i:(0 if i['status']=='verify' else 1 if i.get('preflight_verified_at') else 2,i['created_at']))[0] for rows in groups.values() if rows]

def main():
    import psycopg,requests,wildberries as wb
    from review_telegram_approval import Approval,Repository,sha
    from review_approval_bridge import SQLSource,DurableBridge
    from review_telegram_runtime import CanonicalGuard,TelegramTransport
    from review_approval_executor import Executor,WBAdapter
    from review_approval_backup import snapshot,encrypt
    from stock_deploy_support import OWNER_PUBLIC,seal,error
    worker_cabinet=os.environ.get('REVIEW_WORKER_CABINET') or None
    if worker_cabinet not in (None,'token_1','token_2','token_3'):raise ValueError('Unknown worker cabinet')
    root=os.environ['SUPABASE_SECRET_KEY'].encode()
    pw=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
    with psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=pw,sslmode='require',autocommit=True,connect_timeout=15,options='-c statement_timeout=30000') as conn:
        repo=Repository(conn,postgres=True)
        def config():
            row=conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:telegram-approval:config:v1'").fetchone()
            value=dict(row[0]) if row else {}
            group=conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:content-group:v1'").fetchone()
            if group and group[0].get('enabled') is True and group[0].get('destination_verified') is True:value['content_group_chat_id']=str(group[0]['chat_id']);value['content_group_policy']=group[0]
            return value
        cfg=config()
        if not all(cfg.get(k) for k in ('enabled','publication_enabled','destination_verified')):return {'status':'disabled'}
        app=Approval(repo,base64.b64encode(hmac.new(root,b'veschi:review-approval-ingress:20261015:v1',hashlib.sha256).digest()).decode(),cfg['owner_id'],cfg['chat_id'],cfg['bot_id'],enabled=True)
        bridge=DurableBridge(app,SQLSource(conn));adapter=WBAdapter(wb)
        # Shared setting is only a display flag; process_update never invokes WB.
        os.environ['REVIEW_PUBLICATION_ENABLED']='1'
        report={'wb_writes':0,'checked':{},'errors':{},'legacy_queue_calls':0}
        out=Path(os.environ['RUNNER_TEMP'])/'stock-deploy-proof';out.mkdir(exist_ok=True)
        def preserve():
            (out/'approved-publication-backup.aes.json').write_text(json.dumps(encrypt(snapshot(repo),OWNER_PUBLIC.encode())))
            seal('approved-publication-receipts',report)
        canonical_guard=CanonicalGuard(app,bridge.project)
        def publication_guard(card):
            from review_auto_five_star import authorized_card
            return authorized_card(app,bridge.source,card) and canonical_guard(card)
        executor=Executor(app,publication_guard,adapter,enabled=True,preserve=preserve)
        native=requests.sessions.Session.request;active=None
        def guarded(session,method,url,*args,**kwargs):
            from urllib.parse import urlsplit
            u=urlsplit(str(url));method=method.upper()
            if u.hostname and 'wildberries.' in u.hostname:
                if active is None:raise RuntimeError('Unbound WB request')
                i=active
                getpath='/api/v1/feedback' if i['kind']=='feedbacks' else '/api/v1/question'
                payload=kwargs.get('json') or {}
                valid=(method=='GET' and u.hostname=='feedbacks-api.wildberries.ru' and u.path==getpath and (kwargs.get('params') or {}).get('id')==i['item_id'])
                if i['kind']=='feedbacks':valid=valid or (method=='POST' and u.path=='/api/v1/feedbacks/answer' and payload=={'id':i['item_id'],'text':i['answer']})
                else:valid=valid or (method=='PATCH' and u.path=='/api/v1/questions' and payload=={'id':i['item_id'],'answer':{'text':i['answer']},'state':'wbRu'})
                auth=(kwargs.get('headers') or {}).get('Authorization')
                if not valid or auth!=wb.feedback_token(i['cabinet']):raise RuntimeError('WB request outside approved cabinet/text')
                if method!='GET':
                    saved=repo.get('intents',i['id'])
                    if saved['status']!='verify' or saved['answer_sha256']!=sha(payload.get('text') if i['kind']=='feedbacks' else payload['answer']['text']):raise RuntimeError('Durable write intent unavailable')
                    report['wb_writes']+=1
                    preserve()
            if '/rest/v1/review_replies' in str(url) and method!='GET':raise RuntimeError('Legacy queue mutation forbidden')
            if '/rpc/' in str(url):raise RuntimeError('Legacy queue RPC forbidden')
            response=native(session,method,url,*args,**kwargs)
            if u.hostname and 'wildberries.' in u.hostname:
                with repo.transaction():
                    repo.put('events','approved-worker:wb-http:'+active['cabinet'],dict(checked_at=time.time(),run_id=os.getenv('GITHUB_RUN_ID'),cabinet=active['cabinet'],item_id=active['item_id'],method=method,path=u.path,http_status=response.status_code,rate_headers={k:response.headers.get(k) for k in ('X-RateLimit-Retry','Retry-After','X-RateLimit-Reset','X-RateLimit-Limit','X-RateLimit-Remaining')}))
            from review_auto_five_star import validate_preflight_response
            validate_preflight_response(active,method,url,response)
            return response
        requests.sessions.Session.request=guarded
        try:
            from review_approval_cleanup import cleanup_completed
            cleanup_completed(app,TelegramTransport(os.environ['TELEGRAM_BOT_TOKEN']),preserve,cabinet=worker_cabinet)
            deadline=time.monotonic()+25*60
            while time.monotonic()<deadline:
                cfg=config();app.group=cfg.get('content_group_policy',{})
                if not all(cfg.get(k) for k in ('enabled','publication_enabled','destination_verified')):break
                # Catch clicks even if their GitHub dispatch was unavailable. The
                # UI lock is released BEFORE WB HTTP, so receipt never waits on WB.
                locked=conn.execute("SELECT pg_try_advisory_lock(hashtextextended('review-approval-process-ui-v1',0))").fetchone()[0]
                if locked:
                    try:
                        from review_approval_inbox import drain
                        report['inbox']=drain(app,bridge,TelegramTransport(os.environ['TELEGRAM_BOT_TOKEN']),app.secret,preserve=preserve,new_notices_enabled=cfg.get('new_notices_enabled') is True,cutover=cfg['cutover'])
                    finally:conn.execute("SELECT pg_advisory_unlock(hashtextextended('review-approval-process-ui-v1',0))")
                # Library maintenance is independent of WB publication and cannot undo approval.
                try:
                    from review_approved_benchmarks import sync_live
                    report['benchmarks']=sync_live(repo,str(cfg['owner_id']))
                except Exception as exc:
                    report['benchmarks']={'error_type':type(exc).__name__}
                pending=due_intents(repo,cfg,cabinet=worker_cabinet)
                for intent in pending:
                    if intent.get('worker_retry_at',0)>time.time():continue
                    if adapter.pause(intent['cabinet']) or intent.get('retry_at',0)>time.time():continue
                    try:
                        app.chat=str(intent['chat_id']);active=intent;preserve()
                        from review_approval_card_delivery import notify_owner_receipt
                        receipt_transport=TelegramTransport(os.environ['TELEGRAM_BOT_TOKEN'])
                        notify_owner_receipt(app,receipt_transport,intent,preserve)
                        outcome=executor.run(intent['id'])
                        if outcome.get('busy'):continue
                        report['checked'][intent['id']]={'cabinet':intent['cabinet'],'item_id':intent['item_id'],'status':outcome['status'],'retry_at':outcome.get('retry_at'),'actual_answer_sha256':outcome.get('actual_answer_sha256'),'answer_sha256':intent['answer_sha256']}
                        with repo.transaction():
                            card=repo.get('cards',intent['card_token'],lock=True)
                            card.update(status={'confirmed':'sent','manual_present':'manual_present','verify':'uncertain','blocked':'held'}.get(outcome['status'],'approved'),publication_enabled=True,retry_at=outcome.get('retry_at',0))
                            repo.put('cards',intent['card_token'],card)
                        notify_owner_receipt(app,receipt_transport,outcome,preserve)
                        preserve()
                        report['errors'].pop(intent['id'],None)
                    except Exception as exc:
                        report['errors'][intent['id']]=error(exc)
                        # One cabinet outage must not stop the other two. Never
                        # reset publication/verify state or repeat an unknown POST.
                        with repo.transaction():
                            saved=repo.get('intents',intent['id'],lock=True)
                            failures=saved.get('worker_failures',0)+1
                            saved.update(worker_failures=failures,worker_retry_at=time.time()+min(300,10*2**min(failures,5)),worker_error_type=type(exc).__name__)
                            repo.put('intents',intent['id'],saved)
                        preserve()
                    finally:
                        active=None;app.chat=app.legacy_chat
                # Stay available while idle; GitHub schedules can be delayed.
                with repo.transaction():
                    health=dict(checked_at=time.time(),run_id=os.getenv('GITHUB_RUN_ID'),code_commit=os.getenv('GITHUB_SHA'),auto_policy_code_version='positive-verified-descriptions-20261031',worker_cabinet=worker_cabinet,pending_cabinets=len(pending),inbox=report.get('inbox',{}),errors=len(report['errors']),legacy_queue_calls=0)
                    repo.put('events','approved-worker:health:v1',health)
                    if worker_cabinet:repo.put('events','approved-worker:health:v1:'+worker_cabinet,health)
                time.sleep(10)
            preserve()
            counts={}
            for r in report['checked'].values():counts[r['status']]=counts.get(r['status'],0)+1
            return {'states':counts,'pending':len(due_intents(repo,cfg,cabinet=worker_cabinet)),'errors':len(report['errors']),'legacy_queue_calls':0}
        finally:requests.sessions.Session.request=native

if __name__=='__main__':
    hidden=io.StringIO()
    try:
        with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):result=main()
        print(json.dumps(result))
        if result.get('errors'):raise SystemExit(1)
    except Exception as exc:
        from stock_deploy_support import seal,error
        seal('approved-publication-failure',{'error':error(exc),'private_log':hidden.getvalue()})
        print('Approved review worker failed; diagnostic protected.');raise SystemExit(1)



