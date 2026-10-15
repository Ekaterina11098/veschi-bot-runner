"""Recover the owner's exact visible variant-1 confirmation after stale nonce failure.
Only the fixed card / version / SHA below. Never fabricate a Telegram event.
"""
import os,json,time
from pathlib import Path
import psycopg,wildberries
from review_telegram_approval import Approval,Repository,Rejected,sha
from review_approval_bridge import SQLSource,DurableBridge
from review_telegram_runtime import CanonicalGuard,TelegramTransport
from review_approval_process import process
from review_approval_executor import WBAdapter
from review_approval_backup import snapshot,encrypt
TOKEN='359dfd9c3eee92d596247c388dd9b6f4'
EXPECTED='9b224203e606ce4c6a132f2d782f86b20e24e8830e329883bf948829f5005e5d'
VERSION='owner-telegram-first-20261015-1792066028'
conn=psycopg.connect(os.environ['REVIEW_APPROVAL_DSN'],autocommit=True,connect_timeout=15,options='-c statement_timeout=30000')
out=Path(os.environ['RUNNER_TEMP'])/'review-approval-output';out.mkdir(exist_ok=True)
repo=Repository(conn,postgres=True)
a=Approval(repo,os.environ['REVIEW_APPROVAL_INGRESS_KEY'],os.environ['REVIEW_APPROVAL_OWNER_ID'],os.environ['TELEGRAM_ALLOWED_CHAT_ID'],os.environ['REVIEW_APPROVAL_BOT_ID'],enabled=True)
bridge=DurableBridge(a,SQLSource(conn))
def preserve():
    (out/'approval-supplement.aes.json').write_text(json.dumps(encrypt(snapshot(repo),os.environ['RECOVERY_PUBLIC_KEY'].encode())))
try:
    conn.execute("SELECT pg_advisory_lock(hashtextextended('review-approval-process-ui-v1',0))")
    card=repo.get('cards',TOKEN)
    assert card and card['cabinet']=='token_1' and card['kind']=='feedbacks'
    assert card['version']==VERSION and card['message_id']==646 and card['hashes'][0]==EXPECTED and sha(card['texts'][0])==EXPECTED
    iid=sha([card['ref'],card['version'],EXPECTED])
    if not repo.get('intents',iid):
        assert CanonicalGuard(a,bridge.project)(card)
        with repo.transaction():
            item=repo.get('items',card['ref'],lock=True);card=repo.get('cards',TOKEN,lock=True)
            assert item['status']=='open' and item['token']==TOKEN and card['status']=='selected' and card['selected']==0
            assert time.time()<card['expires_at']
            intent={'id':iid,'ref':card['ref'],'cabinet':card['cabinet'],'kind':card['kind'],'item_id':card['item_id'],'version':VERSION,'answer':card['texts'][0],'answer_sha256':EXPECTED,'source_sha256':sha(card['source']),'owner_id':a.owner,'chat_id':a.chat,'status':'awaiting_preflight','created_at':time.time(),'card_token':TOKEN,'authorization_source':'owner_chat_recovery','authorization_evidence':{'owner_reported_confirm_click':True,'screenshot_message_id':646,'selected_variant':1,'failed_run':38734401627,'failure':'Outdated confirmation','original_selection_events':['3554943945523907184','3554943943142644140']}}
            repo.put('intents',iid,intent);card['status']='approved';item['status']='approved'
            repo.put('cards',TOKEN,card);repo.put('items',card['ref'],item)
            repo.put('events','owner-chat-recovery:20261015:'+TOKEN,{'created_at':time.time(),'result':{'decision':'approved','intent_id':iid},'authorization_source':'owner_chat_recovery','answer_sha256':EXPECTED})
    preserve()
    result=process(a,bridge,TelegramTransport(os.environ['TELEGRAM_BOT_TOKEN']),WBAdapter(wildberries),{'resume_intent':iid,'owner_id':a.owner,'chat_id':a.chat},publication_enabled=True,preserve=preserve)
    current=repo.get('intents',iid)
    print(json.dumps({'publication_status':current['status'],'retry_at':current.get('retry_at'),'readback_confirmed':current.get('actual_answer_sha256')==EXPECTED,'ui_delivery':result.get('ui_delivery')}))
finally:
    preserve();conn.close()

# Continue same durable intent only after saved RetryAfter 2026-10-15T12:34:58UTC.
