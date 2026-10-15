"""Approved restricted review deployment bootstrap; no WB or Telegram messages."""
import os,json,hmac,hashlib,base64,time
from urllib.parse import quote
import psycopg,requests
from stock_deploy_support import seal,error
report={'wb_calls':0,'telegram_sends':0}
try:
    secret=os.environ['SUPABASE_SECRET_KEY'].encode()
    password=hmac.new(secret,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
    ingress=base64.b64encode(hmac.new(secret,b'veschi:review-approval-ingress:20261015:v1',hashlib.sha256).digest()).decode()
    host='aws-0-eu-central-1.pooler.supabase.com';project='abxgjoqlddhtcmjcjwxw';role='review_approval_login_20261015'
    admin=psycopg.connect(host=host,port=5432,dbname='postgres',user='postgres.'+project,password=os.environ['SUPABASE_DB_PASSWORD'],sslmode='require',connect_timeout=15,autocommit=True)
    from psycopg import sql
    exists=admin.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone()
    if not exists:
        admin.execute(sql.SQL('CREATE ROLE {} LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
        admin.execute(sql.SQL('GRANT review_approval_runtime TO {}').format(sql.Identifier(role)))
    flags=admin.execute('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=%s',(role,)).fetchone()
    assert flags==(False,False,False,False,False)
    dsn='postgresql://'+quote(role+'.'+project,safe='')+':'+password+'@'+host+':5432/postgres?sslmode=require'
    runtime=psycopg.connect(dsn,connect_timeout=15,autocommit=True)
    proof={'technical':True,'purpose':'approved review deployment write/readback','publication_enabled':False,'created_at':time.time()}
    runtime.execute("INSERT INTO review_approval.events(id,payload) VALUES(%s,%s) ON CONFLICT(id) DO NOTHING",('deployment-proof:20261015',json.dumps(proof)))
    actual=json.loads(runtime.execute("SELECT payload FROM review_approval.events WHERE id='deployment-proof:20261015'").fetchone()[0])
    assert actual['technical'] is True and actual['publication_enabled'] is False
    assert runtime.execute("SELECT count(*) FROM review_approval.source_cache").fetchone()[0]>=1
    assert runtime.execute("SELECT count(*) FROM review_approval.source_journal").fetchone()[0]>=1
    assert runtime.execute("SELECT has_table_privilege(current_user,'public.review_replies','UPDATE'),has_table_privilege(current_user,'public.telegram_api_cache','UPDATE'),has_table_privilege(current_user,'review_approval.source_journal','UPDATE')").fetchone()==(False,False,False)
    def tg(method,payload):
        r=requests.post('https://api.telegram.org/bot'+os.environ['TELEGRAM_BOT_TOKEN']+'/'+method,json=payload,timeout=(5,15))
        r.raise_for_status();value=r.json();assert value.get('ok') is True;return value['result']
    bot=tg('getMe',{});chat=tg('getChat',{'chat_id':os.environ['TELEGRAM_ALLOWED_CHAT_ID']})
    assert chat['type']=='private'
    fingerprint=hashlib.sha256((str(chat['id'])+'|'+str(bot['id'])).encode()).hexdigest()
    assert fingerprint=='96e17776da8ff52452990c88c38f1a2d4db9a4bf61f816e852a6ca65e946ea76'
    report.update(role_write_readback=True,role_isolation_verified=True,old_destination_verified=True,
      config={'REVIEW_APPROVAL_DSN':dsn,'REVIEW_APPROVAL_INGRESS_KEY':ingress,'REVIEW_APPROVAL_OWNER_ID':str(chat['id']),'REVIEW_APPROVAL_BOT_ID':str(bot['id'])},
      technical_event=actual,success=True)
    runtime.close();admin.close()
except Exception as exc:report['error']=error(exc)
finally:
    seal('review-approval-deployment',report)
    print(json.dumps({k:report.get(k) for k in ('success','role_write_readback','role_isolation_verified','old_destination_verified','wb_calls','telegram_sends')}))
    if not report.get('success'):raise SystemExit(1)
