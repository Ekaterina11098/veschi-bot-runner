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
        for event_id,raw in repo.execute("SELECT id,payload FROM {p}events WHERE id LIKE 'edit:%'").fetchall():
            event=json.loads(raw)
            if event.get('actor')!=app.owner:continue
            card=repo.get('cards',event.get('token',''))
            if not card or card.get('status')!='rework':continue
            results[event_id]=revise(app,bridge,store,NewNoticeTransport(os.environ['TELEGRAM_BOT_TOKEN']),event_id,preserve,cfg['cutover'])
        preserve()
        print(json.dumps({'revisions':len(results),'confirmed':sum(r.get('status')=='confirmed' for r in results.values()),'wb_writes':0}))
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

