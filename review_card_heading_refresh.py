"""Refresh existing active Telegram cards only; no new cards or WB calls."""
import os,sys,json,hmac,hashlib,base64
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
def main():
    import psycopg
    from review_telegram_approval import Approval,Repository
    from review_telegram_runtime import TelegramTransport
    from review_approval_card_delivery import notify_owner_receipt
    from stock_deploy_support import seal
    root=os.environ['SUPABASE_SECRET_KEY'].encode()
    pw=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
    with psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=pw,sslmode='require',autocommit=True,connect_timeout=15) as conn:
        repo=Repository(conn,postgres=True)
        cfg=conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:telegram-approval:config:v1'").fetchone()[0]
        if not cfg.get('enabled') or not cfg.get('destination_verified') or str(cfg['chat_id'])!=os.environ['TELEGRAM_ALLOWED_CHAT_ID']:raise ValueError('Receipt destination unavailable')
        app=Approval(repo,'receipt-only',cfg['owner_id'],cfg['chat_id'],cfg['bot_id'])
        conn.execute("SELECT pg_advisory_lock(hashtextextended('review-approval-process-ui-v1',0))")
        report={'updated':0,'uncertain':0}
        tg=TelegramTransport(os.environ['TELEGRAM_BOT_TOKEN'])
        for token,raw in repo.execute('SELECT id,payload FROM {p}cards').fetchall():
            card=json.loads(raw);item=repo.get('items',card['ref'])
            if card['status'] not in ('awaiting','selected') or not item or item.get('token')!=token:continue
            view=app.view(token)
            try:
                tg.call('editMessageText',{'chat_id':app.chat,'message_id':view['message_id'],'text':view['text'],'reply_markup':view['reply_markup']})
                status='confirmed';report['updated']+=1
            except Exception:
                status='uncertain';report['uncertain']+=1
            with repo.transaction():repo.put('events','card-header-refresh:20261016:'+token,{'status':status,'message_id':card['message_id'],'checked_at':app.clock()})
        seal('telegram-card-heading-refresh',report)
        print(json.dumps(dict(report,wb_writes=0,new_messages=0)))
        if report['uncertain']:raise SystemExit(1)
if __name__=='__main__':main()
