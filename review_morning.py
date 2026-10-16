"""Independent morning review cards. No publication/old worker entry points."""
import os,sys,json,time,hmac,hashlib,base64,contextlib,io
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from pathlib import Path

CABINETS=('token_1','token_2','token_3')

def target_day(now=None,manual=False):
    local=(now or datetime.now(timezone.utc)).astimezone(ZoneInfo('Europe/Moscow'))
    if not manual and not (450 <= local.hour*60+local.minute < 660):return None
    return local.date().isoformat()

def eligible(item,cabinet,source,repo,read_hold):
    from review_telegram_approval import identity
    from review_approval_bridge import reply_key
    item_id=str(item.get('id') or '')
    if not item_id or item.get('isAnswered') is True or (item.get('answer') or {}).get('text','').strip():return False
    if (read_hold('reviews:hold:'+cabinet+':feedbacks:'+item_id) or {}).get('active'):return False
    if source.was_notified(cabinet,'feedbacks',item_id) or source.journal(reply_key(cabinet,'feedbacks',item_id)):return False
    # Any existing card/hold/decision belongs to the existing approval workflow.
    return repo.get('items',identity(cabinet,'feedbacks',item_id)) is None

def main():
    import psycopg,requests
    from stock_deploy_support import seal,OWNER_PUBLIC
    sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
    from review_telegram_approval import Approval,Repository,sha
    from review_approval_bridge import SQLSource,DurableBridge
    from review_approval_notice import NewNotice,NewNoticeTransport
    from review_approval_backup import snapshot,encrypt
    from review_durable_workflow import DurableReviews,generate_and_persist
    from review_queue import _request
    from review_inbox_cache import save_inbox
    import wildberries as wb
    day=target_day(manual=os.getenv('GITHUB_EVENT_NAME') in ('push','workflow_dispatch'))
    if not day:return {'status':'outside_morning_window'}
    root=os.environ['SUPABASE_SECRET_KEY'].encode()
    pw=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
    with psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=pw,sslmode='require',autocommit=True,connect_timeout=15) as conn:
        # Serialize independent morning runs, including manual catch-up.
        if not conn.execute("SELECT pg_try_advisory_lock(hashtextextended('reviews-morning-delivery',0))").fetchone()[0]:return {'status':'busy'}
        repo=Repository(conn,postgres=True)
        cfg=conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:telegram-approval:config:v1'").fetchone()[0]
        if not all(cfg.get(k) for k in ('enabled','new_notices_enabled','destination_verified')):raise RuntimeError('Review notice configuration unavailable')
        if str(cfg['chat_id'])!=os.environ['TELEGRAM_ALLOWED_CHAT_ID']:raise RuntimeError('Destination mismatch')
        app=Approval(repo,base64.b64encode(hmac.new(root,b'veschi:review-approval-ingress:20261015:v1',hashlib.sha256).digest()).decode(),cfg['owner_id'],cfg['chat_id'],cfg['bot_id'],enabled=True)
        source=SQLSource(conn);bridge=DurableBridge(app,source);store=DurableReviews(_request)
        control='reviews-morning:'+day
        state=repo.get('events',control) or {'status':'collecting','date':day,'scopes':{},'items':{},'created_at':time.time(),'telegram_confirmed':0}
        if state['status']=='complete':return {'status':'already_complete','telegram_confirmed':state['telegram_confirmed']}
        def preserve():
            out=Path(os.environ['RUNNER_TEMP'])/'stock-deploy-proof';out.mkdir(exist_ok=True)
            (out/'morning-live-supplement.aes.json').write_text(json.dumps(encrypt(snapshot(repo),OWNER_PUBLIC.encode())))
            seal('reviews-morning',state)
        def save():
            with repo.transaction():repo.put('events',control,state)
            if repo.get('events',control)!=state:raise RuntimeError('Morning state readback mismatch')
            preserve()
        original=requests.sessions.Session.request
        def guard(session,method,url,*args,**kwargs):
            if 'wildberries.' in url and method.upper()!='GET':raise RuntimeError('Morning WB writes forbidden')
            if '/rest/v1/review_replies' in url and method.upper()!='GET':raise RuntimeError('Old queue mutation forbidden')
            if '/rpc/' in url:raise RuntimeError('Old queue RPC forbidden')
            return original(session,method,url,*args,**kwargs)
        requests.sessions.Session.request=guard
        import openai_client as generation
        from openai import OpenAI
        generation.OpenAI=lambda **kw:OpenAI(timeout=90,max_retries=0,**kw)
        transport=NewNoticeTransport(os.environ['TELEGRAM_BOT_TOKEN'])
        notice=NewNotice(app,bridge,transport,enabled=True,preserve=preserve)
        deadline=time.monotonic()+12*60
        try:
            while time.monotonic()<deadline:
                for cabinet in CABINETS:
                    scope=state['scopes'].setdefault(cabinet,{'status':'collecting','items':[],'skip':0})
                    if scope.get('status')=='complete':continue
                    if scope.get('retry_at',0)>time.time():continue
                    try:
                        if scope['status']=='collecting':
                            rows=wb.get_unanswered_feedbacks(take=100,skip=scope['skip'],cabinet=cabinet)
                            scope['items'].extend(rows);scope['skip']+=len(rows)
                            if len(rows)<100:
                                scope.update(status='processing',observed_at=time.time())
                                save_inbox('feedbacks',list({str(x['id']):x for x in scope['items']}.values()),cabinet=cabinet)
                            save()
                            # Respect shared WB cooldown before exact item preflights.
                            continue
                        remaining=False
                        for item in scope['items']:
                            item_id=str(item['id']);key=cabinet+':'+item_id
                            prior=state['items'].get(key,{})
                            if prior.get('status') in ('confirmed','skipped','manual_present','uncertain','error'):continue
                            remaining=True
                            candidate=prior or {'version':'morning-'+day+'-'+sha([cabinet,item_id])[:12],'status':'preflight'}
                            state['items'][key]=candidate
                            if not eligible(item,cabinet,source,repo,store.read):
                                candidate['status']='skipped';save();continue
                            if candidate['status']=='preflight':
                                if wb.get_reply_answer(item_id,'feedbacks',cabinet=cabinet).strip():
                                    candidate['status']='manual_present';save();continue
                                candidate.update(status='generate',preflight_at=time.time());save()
                            if candidate['status']=='generate':
                                # Canonical source and variants are durable before Telegram.
                                version=candidate['version']
                                store.insert('reviews:source:'+sha([cabinet,'feedbacks',item_id,version]),dict(cabinet=cabinet,kind='feedbacks',item_id=item_id,version=version,item=item,source_sha256=sha(item),observed_at=scope['observed_at']))
                                if not store.read(bridge.draft_key(cabinet,'feedbacks',item_id,version)):
                                    generate_and_persist(store,item,cabinet,'feedbacks',version,generation.generate_draft)
                                candidate['status']='notify';save()
                            result=notice.deliver(item,cabinet,'feedbacks',candidate['version'],scope['observed_at'],cfg['cutover'])
                            candidate.update(status='confirmed' if result.get('status')=='confirmed' else 'uncertain',delivery=result)
                            state['telegram_confirmed']+=int(candidate['status']=='confirmed');save()
                            if time.monotonic()>=deadline:break
                        if not remaining or all(state['items'].get(cabinet+':'+str(i['id']),{}).get('status') in ('confirmed','skipped','manual_present','uncertain','error') for i in scope['items']):
                            scope['status']='complete';save()
                    except wb.ReviewRateLimit as exc:
                        scope['retry_at']=time.time()+exc.retry_seconds;scope['last_error']='WB 429';save()
                    except Exception as exc:
                        # Persist redacted diagnostics, keep unrelated cabinets moving.
                        from stock_deploy_support import error
                        scope['last_error']=error(exc);scope['retry_at']=time.time()+300;save()
                if all(state['scopes'].get(c,{}).get('status')=='complete' for c in CABINETS):
                    summary=repo.get('events',control+':summary')
                    if summary is None:
                        names={'token_1':'ООО','token_2':'ИП','token_3':'Китай'}
                        text='📩 Утренние отзывы · '+day+'\n'
                        text+='\n'.join(names[c]+': без ответа в WB — '+str(len(state['scopes'][c]['items'])) for c in CABINETS)
                        text+='\nНовых карточек отправлено: '+str(state['telegram_confirmed'])+'. Уже присланные и отложенные повторно не отправлялись.\nhttps://veschi-ai.streamlit.app/review_manager'
                        summary={'status':'sending','created_at':time.time()}
                        with repo.transaction():repo.put('events',control+':summary',summary)
                        preserve()
                        try:
                            response=transport.call('sendMessage',{'chat_id':app.chat,'text':text})
                            if str(response.get('chat',{}).get('id'))!=app.chat or not response.get('message_id'):raise RuntimeError('Summary unconfirmed')
                            summary.update(status='confirmed',message_id=response['message_id'])
                        except Exception:summary['status']='uncertain'
                        with repo.transaction():repo.put('events',control+':summary',summary)
                        preserve()
                    state['summary']=summary
                    state['status']='complete';save();break
                if time.monotonic()+30>=deadline:break
                time.sleep(30)
            state['checked_at']=datetime.now(timezone.utc).isoformat();save()
            return {'status':state['status'],'telegram_confirmed':state['telegram_confirmed'],'cabinet_statuses':{c:s['status'] for c,s in state['scopes'].items()}}
        finally:requests.sessions.Session.request=original

if __name__=='__main__':
    private_log=io.StringIO()
    try:
        with contextlib.redirect_stdout(private_log),contextlib.redirect_stderr(private_log):result=main()
        print(json.dumps(result))
    except Exception as exc:
        from stock_deploy_support import seal,error
        seal('reviews-morning-error',{'error':error(exc),'private_log':private_log.getvalue()})
        print('Morning reviews failed; protected diagnostic saved.');raise SystemExit(1)

