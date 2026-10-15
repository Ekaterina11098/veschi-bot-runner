"""Remove only the owner-approved card646; no WB client or request."""
import os,json
from pathlib import Path
import psycopg
from review_telegram_approval import Approval,Repository
from review_telegram_runtime import TelegramTransport
from review_approval_card_delivery import dismiss_approved
from review_approval_backup import snapshot,encrypt
conn=psycopg.connect(os.environ['REVIEW_APPROVAL_DSN'],autocommit=True,connect_timeout=15,options='-c statement_timeout=30000')
repo=Repository(conn,postgres=True)
a=Approval(repo,os.environ['REVIEW_APPROVAL_INGRESS_KEY'],os.environ['REVIEW_APPROVAL_OWNER_ID'],os.environ['TELEGRAM_ALLOWED_CHAT_ID'],os.environ['REVIEW_APPROVAL_BOT_ID'],enabled=True)
out=Path(os.environ['RUNNER_TEMP'])/'review-approval-output';out.mkdir(exist_ok=True)
def preserve():
    (out/'approval-supplement.aes.json').write_text(json.dumps(encrypt(snapshot(repo),os.environ['RECOVERY_PUBLIC_KEY'].encode())))
try:
    conn.execute("SELECT pg_advisory_lock(hashtextextended('review-approval-process-ui-v1',0))")
    token='359dfd9c3eee92d596247c388dd9b6f4'
    card=repo.get('cards',token)
    assert card['message_id']==646 and card['hashes'][0]=='9b224203e606ce4c6a132f2d782f86b20e24e8830e329883bf948829f5005e5d'
    result=dismiss_approved(a,TelegramTransport(os.environ['TELEGRAM_BOT_TOKEN']),token,preserve)
    print(json.dumps({'card_removal':result['status'],'wb_calls':0}))
finally:
    preserve();conn.close()
