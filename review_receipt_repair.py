"""Repair the missing owner receipt for the already published last revision."""
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
        intent=repo.get('intents','406e4a268aae2e7c33053887687867fff45151dcd2c766de8b3491d3b587f6d1')
        if intent['status']!='confirmed' or intent.get('wb_ui_status')!='Опубликован для всех' or intent.get('public_actual_answer')!=intent['answer']:raise ValueError('Exact public receipt required')
        def preserve():
            seal('last-revision-owner-receipt',{'intent_id':intent['id'],'events':[row for row in repo.execute("SELECT id,payload FROM {p}events WHERE id LIKE ?",('owner-receipt:'+intent['id']+':%',)).fetchall()]})
        result=notify_owner_receipt(app,TelegramTransport(os.environ['TELEGRAM_BOT_TOKEN']),intent,preserve)
        print(json.dumps({'receipt':result['status'],'wb_writes':0}))
        if result['status']!='confirmed':raise SystemExit(1)
if __name__=='__main__':main()
