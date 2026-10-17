"""Owner-authorized cleanup of tracked Telegram review notices; no WB calls."""
import os,sys,json,hmac,hashlib,base64
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
def main():
    import psycopg
    from review_telegram_approval import Approval,Repository
    from review_telegram_runtime import TelegramTransport
    from review_approval_cleanup import cleanup_completed
    from stock_deploy_support import seal
    root=os.environ['SUPABASE_SECRET_KEY'].encode()
    pw=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
    with psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=pw,sslmode='require',autocommit=True,connect_timeout=15) as conn:
        repo=Repository(conn,postgres=True)
        cfg=conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:telegram-approval:config:v1'").fetchone()[0]
        if not cfg.get('enabled') or not cfg.get('destination_verified') or str(cfg['chat_id'])!=os.environ['TELEGRAM_ALLOWED_CHAT_ID']:raise ValueError('Receipt destination unavailable')
        app=Approval(repo,'receipt-only',cfg['owner_id'],cfg['chat_id'],cfg['bot_id'])
        conn.execute("SELECT pg_advisory_lock(hashtextextended('review-approval-process-ui-v1',0))")
        report={}
        def preserve():seal('review-telegram-cleanup',report)
        report.update(cleanup_completed(app,TelegramTransport(os.environ['TELEGRAM_BOT_TOKEN']),preserve))
        with repo.transaction():repo.put('events','telegram-cleanup-run:'+str(int(app.clock())),dict(report,checked_at=app.clock(),wb_writes=0))
        preserve()
        print(json.dumps(dict(report,wb_writes=0)))
if __name__=='__main__':main()
