"""Read-only delivery diagnosis. Never polls, deletes updates, or sends messages."""
import os,json,hmac,hashlib,time
from urllib.parse import urlsplit
import requests,psycopg
token=os.environ['TELEGRAM_BOT_TOKEN']
try:
    response=requests.post('https://api.telegram.org/bot'+token+'/getWebhookInfo',timeout=20)
    result=response.json()
except Exception:
    raise SystemExit('Telegram webhook information unavailable')
if not result.get('ok'):raise SystemExit('Telegram rejected read-only webhook diagnosis')
info=result['result']; parsed=urlsplit(info.get('url',''))
safe={k:info.get(k) for k in ('pending_update_count','last_error_date','last_error_message','allowed_updates','max_connections')}
safe.update(checked_at=time.time(),url_host=parsed.hostname,url_path=parsed.path,run_id=os.getenv('GITHUB_RUN_ID'),writes=0)
root=os.environ['SUPABASE_SECRET_KEY'].encode()
password=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
dsn=os.getenv('REVIEW_APPROVAL_DSN') or ('postgresql://review_approval_login_20261015.abxgjoqlddhtcmjcjwxw:'+password+'@aws-0-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require')
with psycopg.connect(dsn,autocommit=True,connect_timeout=15) as conn:
    conn.execute("INSERT INTO review_approval.events(id,payload) VALUES(%s,%s) ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload",('review-webhook-diagnostic:20261021:v1',json.dumps(safe)))
print('Read-only webhook diagnosis saved. No messages or WB requests sent.')
