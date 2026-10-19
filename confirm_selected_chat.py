"""One explicit owner-chat confirmation of current edited texts; never fake a callback."""
import os,sys,json,time,hmac,hashlib,base64,contextlib,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
AUTH='owner-chat-confirmed-selected:20261019:v1'
PLAN=AUTH+':plan'
def confirm(app,guard,token,preserve,expected):
    from review_telegram_approval import sha,Rejected
    repo=app.repo;card=repo.get('cards',token)
    if not card:raise Rejected('Missing selected owner text')
    if card['status'] in ('approved','sent','manual_present','uncertain'):return {'status':'already_recorded'}
    if card['status']!='selected' or card.get('selected') not in (0,1):raise Rejected('Current selected variant required')
    selected=card['selected']
    if card['version']!=expected['version'] or card['hashes'][selected]!=expected['answer_sha256']:raise Rejected('Owner-confirmed snapshot changed')
    if not guard(card):raise Rejected('Current canonical draft/hold mismatch')
    reference={'authorization_channel':'owner_chat','authorization_ref':AUTH,'authorization_text':'все подтверждено, в ТГ нет ничего','card_token':token,'answer_sha256':card['hashes'][selected],'version':card['version'],'owner_id':app.owner,'chat_id':app.chat,'created_at':time.time()}
    with repo.transaction():repo.put('events',AUTH+':'+token,reference)
    preserve()
    with repo.transaction():
        item=repo.get('items',card['ref'],lock=True);current=repo.get('cards',token,lock=True)
        if current!=card or item.get('token')!=token or item.get('status')!='open':raise Rejected('Selected review changed')
        answer=card['texts'][selected]
        if sha(answer)!=card['hashes'][selected]:raise Rejected('Owner text checksum mismatch')
        intent_id=sha([card['ref'],card['version'],sha(answer)])
        if repo.get('intents',intent_id):raise Rejected('Existing approval intent')
        intent=dict(id=intent_id,ref=card['ref'],cabinet=card['cabinet'],kind=card['kind'],item_id=card['item_id'],version=card['version'],answer=answer,answer_sha256=sha(answer),source_sha256=sha(card['source']),owner_id=app.owner,chat_id=app.chat,status='awaiting_preflight',created_at=time.time(),card_token=token,authorization_channel='owner_chat',authorization_ref=AUTH)
        repo.put('intents',intent_id,intent);card.update(status='approved',publication_enabled=True);item['status']='approved'
        repo.put('cards',token,card);repo.put('items',card['ref'],item)
    preserve();return {'status':'approved','intent_id':intent_id}
def main():
    import psycopg
    from review_telegram_approval import Approval,Repository
    from review_approval_bridge import SQLSource,DurableBridge
    from review_telegram_runtime import CanonicalGuard
    from review_approval_card_delivery import dismiss_approved
    from review_telegram_runtime import TelegramTransport
    from review_approval_backup import snapshot
    from stock_deploy_support import seal
    root=os.environ['SUPABASE_SECRET_KEY'].encode();pw=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
    with psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=pw,sslmode='require',autocommit=True,connect_timeout=15) as conn:
        conn.execute("SELECT pg_advisory_lock(hashtextextended('review-approval-process-ui-v1',0))")
        repo=Repository(conn,postgres=True);cfg=conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:telegram-approval:config:v1'").fetchone()[0]
        if not cfg.get('publication_enabled') or not cfg.get('destination_verified'):raise RuntimeError('Publication disabled')
        app=Approval(repo,'owner-chat-authorized',cfg['owner_id'],cfg['chat_id'],cfg['bot_id'],enabled=True)
        bridge=DurableBridge(app,SQLSource(conn));results={}
        def preserve():seal('owner-edited-confirmations',{'results':results,'snapshot':snapshot(repo)})
        plan=repo.get('events',PLAN)
        if not plan or plan.get('authorization_text')!='все подтверждено, в ТГ нет ничего':raise RuntimeError('Explicit owner authorization plan missing')
        for expected in plan['targets']:
            token=expected['token']
            results[token]=confirm(app,CanonicalGuard(app,bridge.project),token,preserve,expected)
            dismiss_approved(app,TelegramTransport(os.environ['TELEGRAM_BOT_TOKEN']),token,preserve)
        preserve();print(json.dumps({'recorded':len(results),'wb_writes':0}))
if __name__=='__main__':
    hidden=io.StringIO()
    try:
        with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):main()
        print(hidden.getvalue().splitlines()[-1])
    except Exception as exc:
        import traceback
        from run_private import save_diagnostic
        save_diagnostic('owner-edited-confirmations',traceback.format_exc())
        print('Owner confirmation recovery failed; protected diagnostic saved.');raise SystemExit(1)

