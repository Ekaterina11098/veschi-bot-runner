"""One private owner-requested question draft; no WB client or publication path."""
import os,sys,json,hmac,hashlib,base64,contextlib,io,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
PLAN='owner-question-rework:20261020:v1:plan'

def validate_target(app,target):
    from review_telegram_approval import Rejected
    card=app.repo.get('cards',target['token'])
    item=app.repo.get('items',card['ref']) if card else None
    if not card or card.get('cabinet')!='token_2' or card.get('kind')!='questions' or card.get('item_id')!=target['item_id'] or card.get('version')!=target['expected_version']:
        raise Rejected('Exact question/version required')
    if not item or item.get('token')!=target['token'] or item.get('status')!='rework' or card.get('status')!='rework':
        raise Rejected('Current question no longer awaiting rework')
    if len(target['texts'])!=2 or any(not isinstance(t,str) or not t.strip() for t in target['texts']) or target['texts'][0]==target['texts'][1]:raise Rejected('Two distinct variants required')
    if any(json.loads(raw).get('ref')==card['ref'] for _,raw in app.repo.execute('SELECT id,payload FROM {p}intents').fetchall()):raise Rejected('Publication intent already exists')
    return card

def main():
    import psycopg
    from review_telegram_approval import Approval,Repository,sha
    from review_approval_bridge import SQLSource,DurableBridge
    from review_approval_notice import NewNotice,NewNoticeTransport
    from review_approval_backup import snapshot
    from review_durable_workflow import DurableReviews
    from review_queue import _request
    from validator import validate_answer
    from stock_deploy_support import seal
    root=os.environ['SUPABASE_SECRET_KEY'].encode()
    password=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
    with psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=password,sslmode='require',autocommit=True,connect_timeout=15) as conn:
        conn.execute("SELECT pg_advisory_lock(hashtextextended('review-approval-process-ui-v1',0))")
        repo=Repository(conn,postgres=True)
        cfg=conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:telegram-approval:config:v1'").fetchone()[0]
        if not all(cfg.get(k) for k in ('enabled','new_notices_enabled','destination_verified')):raise RuntimeError('Verified notices disabled')
        app=Approval(repo,base64.b64encode(hmac.new(root,b'veschi:review-approval-ingress:20261015:v1',hashlib.sha256).digest()).decode(),cfg['owner_id'],cfg['chat_id'],cfg['bot_id'],enabled=True)
        bridge=DurableBridge(app,SQLSource(conn));store=DurableReviews(_request)
        def preserve():seal('owner-question-rework',snapshot(repo))
        previous=repo.get('events',PLAN+':delivery')
        if previous:
            return {'status':previous['status'],'already_recorded':True,'wb_writes':0,'publication_created':False}
        plan=repo.get('events',PLAN)
        if not plan or plan.get('authorization_channel')!='owner_chat' or plan.get('request')!='refer_to_seller_chat_for_completeness_check':raise RuntimeError('Exact owner request unavailable')
        target=plan['target'];card=validate_target(app,target);binding=card.get('binding') or {}
        sources=[s for s in bridge.source.matching(card['cabinet'],'questions',card['item_id'],'reviews:source:') if s.get('version')==card['version'] and sha(s.get('item'))==binding.get('raw_source_sha256')]
        if len(sources)!=1:raise RuntimeError('Exact original question unavailable')
        item=sources[0]['item'];check=dict(item,productValuation=0)
        if any(not validate_answer(text,check)['approved'] for text in target['texts']):raise RuntimeError('Question variants failed validation')
        version=card['version']+'-owner-question-rework-20261020-v1';stamp=time.time()
        store.insert('reviews:source:'+sha([card['cabinet'],'questions',card['item_id'],version]),dict(cabinet=card['cabinet'],kind='questions',item_id=card['item_id'],version=version,item=item,source_sha256=sha(item),observed_at=stamp))
        store.insert(bridge.draft_key(card['cabinet'],'questions',card['item_id'],version),dict(schema_version=1,cabinet=card['cabinet'],kind='questions',item_id=card['item_id'],version=version,source_sha256=sha(item),variants=target['texts'],confirmation_status='draft',approved_variant=None,authorization_ref=PLAN))
        preserve()
        result=NewNotice(app,bridge,NewNoticeTransport(os.environ['TELEGRAM_BOT_TOKEN']),enabled=True,preserve=preserve).deliver(item,card['cabinet'],'questions',version,stamp,cfg['cutover'])
        with repo.transaction():repo.put('events',PLAN+':delivery',dict(result,wb_writes=0,publication_created=False))
        preserve()
        if result.get('status')!='confirmed' or result.get('buttons')!='confirmed':raise RuntimeError('Draft delivery uncertain; do not resend')
        return {'status':'confirmed','cards':1,'variants':2,'wb_writes':0,'publication_created':False}

if __name__=='__main__':
    hidden=io.StringIO()
    try:
        with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):result=main()
        print(json.dumps(result))
    except Exception as exc:
        from stock_deploy_support import seal,error
        seal('owner-question-rework-error',{'error':error(exc),'private_log':hidden.getvalue()})
        print('Question draft delivery failed; diagnostic protected.');raise SystemExit(1)
