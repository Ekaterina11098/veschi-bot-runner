"""Only immutable Telegram approvals after the configured cutover; no old queues."""
import os,sys,json,time,hmac,hashlib,base64,contextlib,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))

def due_intents(repo,cfg):
    rows=repo.execute('SELECT id,payload FROM {p}intents').fetchall()
    groups={c:[] for c in ('token_1','token_2','token_3')}
    for intent_id,raw in rows:
        i=json.loads(raw)
        if (i.get('cabinet') not in groups or i.get('status') not in ('awaiting_preflight','verify') or
            i.get('created_at',0)<cfg['cutover'] or str(i.get('owner_id'))!=str(cfg['owner_id']) or str(i.get('chat_id'))!=str(cfg['chat_id'])):continue
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
    root=os.environ['SUPABASE_SECRET_KEY'].encode()
    pw=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
    with psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=pw,sslmode='require',autocommit=True,connect_timeout=15,options='-c statement_timeout=30000') as conn:
        repo=Repository(conn,postgres=True)
        def config():
            row=conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:telegram-approval:config:v1'").fetchone()
            return row[0] if row else {}
        cfg=config()
        if not all(cfg.get(k) for k in ('enabled','publication_enabled','destination_verified')):return {'status':'disabled'}
        app=Approval(repo,base64.b64encode(hmac.new(root,b'veschi:review-approval-ingress:20261015:v1',hashlib.sha256).digest()).decode(),cfg['owner_id'],cfg['chat_id'],cfg['bot_id'],enabled=True)
        bridge=DurableBridge(app,SQLSource(conn));adapter=WBAdapter(wb)
        report={'wb_writes':0,'checked':{},'errors':{},'legacy_queue_calls':0}
        out=Path(os.environ['RUNNER_TEMP'])/'stock-deploy-proof';out.mkdir(exist_ok=True)
        def preserve():
            (out/'approved-publication-backup.aes.json').write_text(json.dumps(encrypt(snapshot(repo),OWNER_PUBLIC.encode())))
            seal('approved-publication-receipts',report)
        executor=Executor(app,CanonicalGuard(app,bridge.project),adapter,enabled=True,preserve=preserve)
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
            return native(session,method,url,*args,**kwargs)
        requests.sessions.Session.request=guarded
        try:
            deadline=time.monotonic()+33*60
            while time.monotonic()<deadline:
                cfg=config()
                if not cfg.get('publication_enabled'):break
                pending=due_intents(repo,cfg)
                if not pending:break
                for intent in pending:
                    if intent['id'] in report['errors']:continue
                    if adapter.pause(intent['cabinet']) or intent.get('retry_at',0)>time.time():continue
                    locked=conn.execute("SELECT pg_try_advisory_lock(hashtextextended('review-approval-process-ui-v1',0))").fetchone()[0]
                    if not locked:continue
                    try:
                        active=intent;preserve()
                        outcome=executor.run(intent['id'])
                        report['checked'][intent['id']]={'cabinet':intent['cabinet'],'item_id':intent['item_id'],'status':outcome['status'],'retry_at':outcome.get('retry_at'),'actual_answer_sha256':outcome.get('actual_answer_sha256'),'answer_sha256':intent['answer_sha256']}
                        with repo.transaction():
                            card=repo.get('cards',intent['card_token'],lock=True)
                            card.update(status={'confirmed':'sent','manual_present':'manual_present','verify':'uncertain','blocked':'held'}.get(outcome['status'],'approved'),publication_enabled=True,retry_at=outcome.get('retry_at',0))
                            repo.put('cards',intent['card_token'],card)
                        preserve()
                    except Exception as exc:report['errors'][intent['id']]=error(exc);preserve()
                    finally:
                        active=None
                        conn.execute("SELECT pg_advisory_unlock(hashtextextended('review-approval-process-ui-v1',0))")
                if report['errors']:break
                time.sleep(30)
            preserve()
            counts={}
            for r in report['checked'].values():counts[r['status']]=counts.get(r['status'],0)+1
            return {'states':counts,'pending':len(due_intents(repo,cfg)),'errors':len(report['errors']),'legacy_queue_calls':0}
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

