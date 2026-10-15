"""Single approved first NEW review notice. WB GET only, no old queue processing."""
import os,sys,json,time,contextlib,io,hmac,hashlib,base64
from datetime import datetime,timezone
from pathlib import Path
import psycopg,requests
from stock_deploy_support import seal,error,OWNER_PUBLIC
sys.path.insert(0,str(Path(os.environ['GITHUB_WORKSPACE'])/'approval-core/review-approval-preparation'))
from review_telegram_approval import Approval,Repository,sha
from review_approval_bridge import SQLSource,DurableBridge
from review_approval_notice import NewNotice,NewNoticeTransport
from review_approval_backup import snapshot,encrypt
from review_durable_workflow import DurableReviews,generate_and_persist
from review_queue import _request
from review_inbox_cache import save_inbox,load_inbox
import wildberries as wb
report={'wb_writes':0,'telegram_attempts':0,'old_queues_processed':0,'scopes':{}}
original=requests.sessions.Session.request
def guarded(self,method,url,*args,**kwargs):
    if 'wildberries.ru' in url and method.upper()!='GET':raise RuntimeError('WB publications forbidden in controlled button pass')
    if '/rest/v1/review_replies' in url and method.upper()!='GET':raise RuntimeError('Old review queue writes forbidden')
    if '/rpc/' in url:raise RuntimeError('Old queue RPC forbidden')
    return original(self,method,url,*args,**kwargs)
requests.sessions.Session.request=guarded
hidden=io.StringIO();runtime=None
try:
    with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
        root=os.environ['SUPABASE_SECRET_KEY'].encode()
        pw=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
        runtime=psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=pw,sslmode='require',autocommit=True,connect_timeout=15)
        repo=Repository(runtime,postgres=True)
        cfg=runtime.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:telegram-approval:config:v1'").fetchone()[0]
        assert cfg['enabled'] and cfg['new_notices_enabled'] and not cfg['publication_enabled']
        app=Approval(repo,base64.b64encode(hmac.new(root,b'veschi:review-approval-ingress:20261015:v1',hashlib.sha256).digest()).decode(),cfg['owner_id'],cfg['chat_id'],cfg['bot_id'],enabled=True)
        bridge=DurableBridge(app,SQLSource(runtime));store=DurableReviews(_request)
        control='first-new-review:20261015'
        state=repo.get('events',control) or {'status':'collecting','scopes':{},'created_at':time.time()}
        def preserve():
            sealed=encrypt(snapshot(repo),OWNER_PUBLIC.encode())
            out=Path(os.environ['RUNNER_TEMP'])/'stock-deploy-proof/approval-live-supplement.aes.json';out.write_text(json.dumps(sealed))
        def save():
            with repo.transaction():repo.put('events',control,state)
            assert repo.get('events',control)==state
            preserve()
        if state['status'] in ('complete','uncertain','no_new_review','error'):
            report['status']=state['status'];report['state']=state
        else:
            if not state.get('candidate'):
                for cabinet in ('token_1','token_2','token_3'):
                    prior=state['scopes'].get(cabinet,{})
                    if prior.get('status')=='fresh':continue
                    pause=wb.review_pause_seconds(cabinet=cabinet)
                    if pause:
                        state['scopes'][cabinet]={'status':'paused','retry_after':pause};continue
                    try:
                        items=wb.get_unanswered_feedbacks(take=100,skip=0,cabinet=cabinet)
                        if len(items)>=100:raise RuntimeError('Inbox not proven complete; do not overwrite a partial list')
                        save_inbox('feedbacks',items,cabinet=cabinet)
                        actual,stamp=load_inbox('feedbacks',cabinet=cabinet)
                        assert sha(actual)==sha(items)
                        state['scopes'][cabinet]={'status':'fresh','count':len(items),'stamp':stamp,'full_sha256':sha(items)}
                        for item in items:
                            item_id=str(item.get('id',''))
                            if not item_id or item_id in ('soHH5MsaEY08FASqdqtM','PwB5eXmFztbgyBhGctsP'):continue
                            hold=store.read('reviews:hold:'+cabinet+':feedbacks:'+item_id)
                            if (hold or {}).get('active') or bridge.source.was_notified(cabinet,'feedbacks',item_id):continue
                            if bridge.source.journal(item_id if cabinet=='token_1' else 'veschi-review:'+cabinet+':feedbacks:'+item_id):continue
                            if item.get('isAnswered') is True or (isinstance(item.get('answer'),dict) and item['answer'].get('text','').strip()):continue
                            state['candidate']={'cabinet':cabinet,'item':item,'version':'owner-telegram-first-20261015-'+str(int(time.time())),'observed_at':time.time()}
                            state['status']='preflight';break
                        save()
                        if state.get('candidate'):break
                    except wb.ReviewRateLimit as exc:
                        state['scopes'][cabinet]={'status':'paused','retry_after':exc.retry_seconds};save()
                if not state.get('candidate'):
                    state['status']='no_new_review' if all(state['scopes'].get(c,{}).get('status')=='fresh' for c in ('token_1','token_2','token_3')) else 'waiting_retry'
                    save()
            if state.get('candidate'):
                candidate=state['candidate'];cabinet=candidate['cabinet'];item=candidate['item'];item_id=str(item['id'])
                pause=wb.review_pause_seconds(cabinet=cabinet)
                if state['status']=='preflight':
                    if pause:state['retry_after']=pause;save()
                    else:
                        actual=wb.get_reply_answer(item_id,'feedbacks',cabinet=cabinet)
                        if actual.strip():state.update(status='manual_present',manual_answer_sha256=sha(actual));save()
                        else:state.update(status='generate',preflight_at=time.time());save()
                if state['status']=='generate':
                    source_key='reviews:source:'+sha([cabinet,'feedbacks',item_id,candidate['version']])
                    store.insert(source_key,{'cabinet':cabinet,'kind':'feedbacks','item_id':item_id,'version':candidate['version'],'item':item,'source_sha256':sha(item),'observed_at':candidate['observed_at']})
                    draft_key=bridge.draft_key(cabinet,'feedbacks',item_id,candidate['version'])
                    if not store.read(draft_key):
                        import openai_client as generation
                        from openai import OpenAI
                        generation.OpenAI=lambda **kw:OpenAI(timeout=90,max_retries=0,**kw)
                        generate_and_persist(store,item,cabinet,'feedbacks',candidate['version'],generation.generate_draft)
                    state['status']='notify';save()
                if state['status']=='notify':
                    report['telegram_attempts']+=1
                    result=NewNotice(app,bridge,NewNoticeTransport(os.environ['TELEGRAM_BOT_TOKEN']),enabled=True,preserve=preserve).deliver(item,cabinet,'feedbacks',candidate['version'],candidate['observed_at'],cfg['cutover'])
                    state['notice']=result;state['status']='complete' if result.get('status')=='confirmed' else 'uncertain';save()
            report['state']=state;report['status']=state['status']
except wb.ReviewRateLimit as exc:report['retry_after']=exc.retry_seconds
except Exception as exc:report['error']=error(exc)
finally:
    if runtime:
        try:preserve()
        except Exception as exc:report['backup_error']=error(exc)
        runtime.close()
    report['private_log']=hidden.getvalue();seal('review-approval-first-new',report)
    print(json.dumps({'status':report.get('status'),'wb_writes':0,'telegram_attempts':report['telegram_attempts'],'error_type':report.get('error',{}).get('type'),'retry_after':report.get('retry_after')}))

# Continue saved exact new-review preflight after WB pause 2026-10-15T12:08:07.625236Z; no repeated list collection.
