"""Read-only audit of live report recipients after a proven Telegram migration."""
import os,sys,json,requests,hmac,hashlib
from datetime import datetime,timezone
from urllib.parse import urlparse
sys.path.insert(0,'private-source')
from advertising_agent import agent_store as store
from stock_deploy_support import seal
OLD=-5533733230;NEW=-1004378639510
proof=dict(complete=False,source_calls=0,model_calls=0,telegram_sends=0,wb_writes=0,configuration_writes=0,checks={})
native=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
def guard(self,method,url,*args,**kwargs):
 if urlparse(url).hostname==host and method.upper()=='GET' and urlparse(url).path.startswith('/rest/v1/'):pass
 elif urlparse(url).hostname=='api.telegram.org' and urlparse(url).path.rsplit('/',1)[-1] in ('getMe','getChat','getChatMember','getChatAdministrators','getWebhookInfo'):pass
 else:raise RuntimeError('Only retained DB and Telegram identity reads allowed')
 return native(self,method,url,*args,**kwargs)
requests.sessions.Session.request=guard
try:
 r=store.registration();proof['advertising_registration']=r
 check=proof['checks'];check['advertising_registration_new']=r['chat_id']==NEW
 profiles={}
 for key in ('advertising:ip:daily_rollout:v1','advertising:ip:limited_rollout:v1','advertising:dialog_rollout:v1','advertising:ip:employee_access:v1'):
  rows=store.db('GET','telegram_api_cache',params={'cache_key':'eq.'+key,'select':'payload,expires_at','limit':1}) or []
  if rows:
   p=rows[0]['payload']
   profiles[key]={k:p.get(k) for k in ('chat_id','owner_id','enabled','telegram_delivery_approved','source_sha','schedule_not_before')}
   profiles[key]['expires_at']=rows[0]['expires_at']
  else:profiles[key]=None
 proof['profiles']=profiles
 check['daily_scope_new']=(profiles.get('advertising:ip:daily_rollout:v1') or {}).get('chat_id')==NEW
 check['limited_delivery_scope_new']=(profiles.get('advertising:ip:limited_rollout:v1') or {}).get('chat_id')==NEW
 check['daily_still_enabled']=(profiles.get('advertising:ip:daily_rollout:v1') or {}).get('enabled') is True
 check['limited_delivery_still_approved']=(profiles.get('advertising:ip:limited_rollout:v1') or {}).get('telegram_delivery_approved') is True
 proof['business_configs']=store.db('GET','business_agent_config',params={'active':'eq.true','select':'agent_id,chat_id,owner_user_id,bot_id,active','limit':20}) or []
 check['other_active_agent_configs_not_old']=all(str(x.get('chat_id'))!=str(OLD) for x in proof['business_configs'])
 general=os.environ.get('TELEGRAM_ALLOWED_CHAT_ID','').strip()
 proof['stock_reviews_environment']=dict(configured=bool(general),is_old_advertising_chat=general==str(OLD),is_new_advertising_chat=general==str(NEW))
 check['stock_reviews_separate_recipient']=bool(general) and general not in (str(OLD),str(NEW))
 import psycopg
 root=os.environ['SUPABASE_SECRET_KEY'].encode()
 pw=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
 with psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=pw,sslmode='require',autocommit=True,connect_timeout=15,options='-c default_transaction_read_only=on') as conn:
  row=conn.execute("SELECT payload->>'chat_id',payload->>'enabled',payload->>'new_notices_enabled',payload->>'destination_verified' FROM review_approval.source_cache WHERE cache_key='reviews:telegram-approval:config:v1'").fetchone()
  if not row:raise RuntimeError('Review recipient config missing')
  proof['review_config']=dict(matches_existing_environment=row[0]==general,is_old_advertising_chat=row[0]==str(OLD),enabled=row[1],new_notices_enabled=row[2],destination_verified=row[3])
  check['review_recipient_matches_existing_environment']=row[0]==general
  check['review_notices_still_enabled']=all(x=='true' for x in row[1:])
 token=os.environ['CHINA_TELEGRAM_BOT_TOKEN'];cfg=next(x for x in proof['business_configs'] if x['agent_id']=='china')
 def tg(method,**kw):return requests.post('https://api.telegram.org/bot'+token+'/'+method,json=kw,timeout=25).json()
 me=tg('getMe');proof['china_identity']=me;check['china_exact_bot']=me.get('result',{}).get('id')==8780468043
 old=cfg['chat_id'];diag={}
 for m in ('getChat','getChatMember','getChatAdministrators'):
  diag[m]=tg(m,chat_id=old,**({'user_id':8780468043} if m=='getChatMember' else {}))
 proof['china_old_telegram']=diag
 candidates=set()
 for val in diag.values():
  nxt=val.get('parameters',{}).get('migrate_to_chat_id')
  if nxt:candidates.add(nxt)
 proof['china_migration_candidates']=list(candidates)
 if len(candidates)==1:
  new=next(iter(candidates));proof['china_new_telegram']={m:tg(m,chat_id=new,**({'user_id':8780468043} if m=='getChatMember' else {})) for m in ('getChat','getChatMember','getChatAdministrators')}
 proof['china_watches']=store.db('GET','telegram_api_cache',params={'cache_key':'like.china_agent:conversion_watch:v1:*','select':'cache_key,payload','limit':100}) or []
 proof['china_recent_jobs']=store.db('GET','business_agent_jobs',params={'agent_id':'eq.china','select':'id,update_id,chat_id,sender_id,request_text,status,created_at','order':'id.desc','limit':12}) or []
 proof['complete']=all(check.values())
except Exception as exc:proof.update(error_type=type(exc).__name__,error=str(exc)[:180])
seal('advertising-dialog-activation',proof)
print(json.dumps({k:proof.get(k) for k in ('complete','checks','source_calls','telegram_sends','wb_writes','configuration_writes','error')}))
if not proof['complete']:raise SystemExit(1)
