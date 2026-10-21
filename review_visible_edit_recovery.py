"""Restore only two owner edits visible in the supplied screenshot, for approval."""
import os,sys,json,hmac,hashlib,base64
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
PLAN='owner-visible-edit-recovery:20261021:v1:plan'
def main():
    import psycopg
    from review_telegram_approval import Approval,Repository
    from review_approval_bridge import SQLSource,DurableBridge
    from review_approval_notice import NewNoticeTransport
    from review_approval_revision import revise
    from review_approval_backup import snapshot
    from review_durable_workflow import DurableReviews
    from review_queue import _request
    from stock_deploy_support import seal
    root=os.environ['SUPABASE_SECRET_KEY'].encode()
    password=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
    with psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=password,sslmode='require',autocommit=True,connect_timeout=15) as conn:
        conn.execute("SELECT pg_advisory_lock(hashtextextended('review-approval-process-ui-v1',0))")
        repo=Repository(conn,postgres=True)
        cfg=conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:telegram-approval:config:v1'").fetchone()[0]
        if not all(cfg.get(k) for k in ('enabled','new_notices_enabled','destination_verified')):raise RuntimeError('Notices disabled')
        app=Approval(repo,'owner-screenshot-recovery-no-webhook',cfg['owner_id'],cfg['chat_id'],cfg['bot_id'],enabled=True)
        bridge=DurableBridge(app,SQLSource(conn));store=DurableReviews(_request)
        plan=repo.get('events',PLAN)
        if not plan or plan.get('authorization_channel')!='owner_chat' or len(plan.get('targets',[]))!=2:raise RuntimeError('Recovery plan unavailable')
        def preserve():seal('visible-edit-recovery',dict(snapshot=snapshot(repo)))
        results=[]
        for target in plan['targets']:
            key=PLAN+':delivery:'+target['token']
            previous=repo.get('events',key)
            if previous:
                results.append(previous);continue
            old=repo.get('cards',target['token'])
            if not old or old.get('cabinet')!=target['cabinet'] or old.get('item_id')!=target['item_id'] or old.get('version')!=target['expected_version'] or old.get('kind')!='feedbacks' or old.get('message_id')!=target['message_id']:raise RuntimeError('Exact card mismatch')
            if any(json.loads(raw).get('ref')==old['ref'] for _,raw in repo.execute('SELECT id,payload FROM {p}intents').fetchall()):raise RuntimeError('Existing publication intent: recovery blocked')
            edit=app.record_edit(target['token'],cfg['owner_id'],cfg['chat_id'],target['message_id'],target['text'])
            preserve()
            result=revise(app,bridge,store,NewNoticeTransport(os.environ['TELEGRAM_BOT_TOKEN']),edit['revision_event_id'],preserve,cfg['cutover'])
            if result.get('status')!='confirmed' or result.get('buttons')!='confirmed':raise RuntimeError('Delivery not confirmed: do not resend blindly')
            result=dict(result,evidence=plan['evidence'],wb_writes=0,publication_created=False)
            with repo.transaction():repo.put('events',key,result)
            preserve();results.append(result)
        print(json.dumps({'cards_confirmed':len(results),'wb_writes':0,'publication_created':False}))
if __name__=='__main__':main()
