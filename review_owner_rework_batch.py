"""Resume saved owner edits only; no WB client or old queues."""
import os,sys,json,hmac,hashlib,base64,contextlib,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
PLAN='owner-rework-batch:20261020:v1:plan'
def validate_target(app,target):
    from review_telegram_approval import Rejected,sha
    old=app.repo.get('cards',target['token'])
    item=app.repo.get('items',old['ref']) if old else None
    if not old or old.get('cabinet')!=target['cabinet'] or old.get('item_id')!=target['item_id'] or old.get('kind')!='feedbacks':raise Rejected('Target mismatch')
    if not item or item.get('token')!=target['token'] or item.get('status') not in ('open','rework') or old['status'] not in ('awaiting','rework'):raise Rejected('Current item no longer awaiting rework')
    if len(target['texts'])!=2 or any(not isinstance(t,str) or not t.strip() for t in target['texts']) or target['texts'][0]==target['texts'][1]:raise Rejected('Two distinct approval variants required')
    if any(json.loads(raw).get('ref')==old['ref'] for _,raw in app.repo.execute('SELECT id,payload FROM {p}intents').fetchall()):raise Rejected('Existing publication intent')
    return old
def main():
    import psycopg
    from review_telegram_approval import Approval,Repository,sha
    from review_approval_bridge import SQLSource,DurableBridge
    from review_approval_notice import NewNoticeTransport,NewNotice
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
        plan=repo.get('events',PLAN)
        if not plan or plan.get('authorization_channel')!='owner_chat' or len(plan.get('targets',[]))!=4:raise RuntimeError('Explicit four-review rework request missing')
        for target in plan['targets']:
            key='owner-rework-batch:20261020:v1:'+target['token']
            existing=repo.get('events',key)
            if existing:
                results[key]=existing
                continue
            old=validate_target(app,target)
            binding=old.get('binding') or {}
            originals=[s for s in bridge.source.matching(old['cabinet'],'feedbacks',old['item_id'],'reviews:source:') if s.get('version')==old['version'] and sha(s.get('item'))==binding.get('raw_source_sha256')]
            if len(originals)!=1:raise RuntimeError('Exact original source unavailable')
            raw_item=originals[0]['item'];version=old['version']+'-owner-rework-20261020-v1'
            import time
            stamp=time.time()
            store.insert('reviews:source:'+sha([old['cabinet'],'feedbacks',old['item_id'],version]),dict(cabinet=old['cabinet'],kind='feedbacks',item_id=old['item_id'],version=version,item=raw_item,source_sha256=sha(raw_item),observed_at=stamp))
            store.insert(bridge.draft_key(old['cabinet'],'feedbacks',old['item_id'],version),dict(schema_version=1,cabinet=old['cabinet'],kind='feedbacks',item_id=old['item_id'],version=version,source_sha256=sha(raw_item),variants=target['texts'],confirmation_status='draft',approved_variant=None,authorization_ref=PLAN))
            preserve()
            result=NewNotice(app,bridge,NewNoticeTransport(os.environ['TELEGRAM_BOT_TOKEN']),enabled=True,preserve=preserve).deliver(raw_item,old['cabinet'],'feedbacks',version,stamp,cfg['cutover'])
            result=dict(result,previous_card_token=target['token'],version=version,wb_writes=0,publication_created=False)
            with repo.transaction():repo.put('events',key,result)
            results[key]=result;preserve()
        if any(r.get('status')!='confirmed' or r.get('buttons')!='confirmed' for r in results.values()):raise RuntimeError('Some approval card deliveries remain uncertain; do not resend automatically')
        print(json.dumps({'cards':len(results),'variants':8,'confirmed':len(results),'wb_writes':0,'publication_created':False}))
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

