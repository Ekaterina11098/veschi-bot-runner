"""Resume saved owner edits only; no WB client or old queues."""
import os,sys,json,hmac,hashlib,base64,contextlib,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
def main():
    import psycopg
    from review_telegram_approval import Approval,Repository
    from review_approval_bridge import SQLSource,DurableBridge
    from review_approval_notice import NewNoticeTransport
    from review_approval_revision import revise
    from review_approval_backup import snapshot,encrypt
    from review_durable_workflow import DurableReviews
    from review_queue import _request
    from stock_deploy_support import seal,OWNER_PUBLIC
    root=os.environ['SUPABASE_SECRET_KEY'].encode();pw=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
    with psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=pw,sslmode='require',autocommit=True,connect_timeout=15) as conn:
        conn.execute("SELECT pg_advisory_lock(hashtextextended('review-approval-process-ui-v1',0))")
        repo=Repository(conn,postgres=True)
        cfg=conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:telegram-approval:config:v1'").fetchone()[0]
        if not all(cfg.get(k) for k in ('enabled','new_notices_enabled','destination_verified')):raise RuntimeError('Review notices disabled')
        app=Approval(repo,base64.b64encode(hmac.new(root,b'veschi:review-approval-ingress:20261015:v1',hashlib.sha256).digest()).decode(),cfg['owner_id'],cfg['chat_id'],cfg['bot_id'],enabled=True)
        bridge=DurableBridge(app,SQLSource(conn));store=DurableReviews(_request);results={}
        def preserve():
            seal('revision-resume',dict(results=results,snapshot=snapshot(repo)))
        from review_telegram_receiver import Receiver
        from review_telegram_runtime import TelegramTransport,CanonicalGuard
        receiver=Receiver(app,TelegramTransport(os.environ['TELEGRAM_BOT_TOKEN']),CanonicalGuard(app,bridge.project),preserve=preserve)
        from review_approval_revision import ready_owner_text
        events=[(k,json.loads(v)) for k,v in repo.execute('SELECT id,payload FROM {p}events').fetchall()]
        for ingress_id,event in events:
            if not ingress_id.startswith('telegram-ingress:') or event.get('status')!='failed' or event.get('error')!='Expired card':continue
            update=event.get('update') or {};q=update.get('callback_query') or {};data=q.get('data','').split(':')
            if len(data)!=3 or not data[2].startswith('ok.'):continue
            key='owner-confirmation-audit:20261019:'+ingress_id
            if repo.get('events',key):continue
            card=repo.get('cards',data[1]);item=repo.get('items',card['ref']) if card else None
            if not card or not item or item.get('token')!=data[1] or card.get('status')!='selected':continue
            if data[2]!='ok.'+str(card.get('nonce')):continue
            if card['texts'][card['selected']] not in q.get('message',{}).get('text',''):raise RuntimeError('Selected text differs from recorded human confirmation')
            preserve()
            result=receiver.receive(update,app.secret)
            intent_id=result.get('result',{}).get('intent_id')
            intent=repo.get('intents',intent_id) if intent_id else None
            if not intent or intent.get('card_token')!=data[1]:raise RuntimeError('Recovered approval readback failed')
            outcome={'status':'restored','card_token':data[1],'intent_id':intent_id,'wb_writes':0,'source_ingress':ingress_id}
            with repo.transaction():repo.put('events',key,outcome)
            results[key]=outcome;preserve()
        for delivery_id,delivery in events:
            if not delivery_id.startswith('revision-delivery:') or delivery.get('status')!='needs_full_text':continue
            edit_id=delivery.get('revision_event_id');edit=repo.get('events',edit_id) if edit_id else None
            if not edit or not ready_owner_text(edit.get('instruction','')):continue
            card=repo.get('cards',edit.get('token',''));item=repo.get('items',card['ref']) if card else None
            if not card or not item or item.get('token')!=edit['token'] or item.get('status')!='rework':continue
            outcome=revise(app,bridge,store,NewNoticeTransport(os.environ['TELEGRAM_BOT_TOKEN']),edit_id,preserve,cfg['cutover'])
            key='owner-revision-audit:20261019:'+delivery_id
            with repo.transaction():repo.put('events',key,dict(outcome,wb_writes=0))
            results[key]=dict(status=outcome.get('status'),wb_writes=0);preserve()
        preserve()
        print(json.dumps({'recovered':len(results),'confirmed':sum(r.get('status') in ('restored','confirmed') for r in results.values()),'wb_writes':0}))
if __name__=='__main__':
    hidden=io.StringIO()
    try:
        with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
            main()
        print(hidden.getvalue().splitlines()[-1])
    except Exception as exc:
        from stock_deploy_support import seal,error
        import traceback
        from run_private import save_diagnostic
        save_diagnostic('review-revisions',traceback.format_exc())
        seal('revision-resume-error',{'error':error(exc),'private_log':hidden.getvalue()})
        print('Revision delivery failed; diagnostic protected.');raise SystemExit(1)

