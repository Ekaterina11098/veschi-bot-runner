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
 if method.upper()!='GET' or urlparse(url).hostname!=host or not urlparse(url).path.startswith('/rest/v1/'):raise RuntimeError('Only retained DB GET allowed')
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
 paths=('chat_id','expected_chat_id','registered_chat_id','recipient_chat_id','telegram_chat_id')
 clauses=['payload->>'+p+'.eq.'+str(OLD) for p in paths]+['cache_key.like.*'+str(OLD)+'*']
 selected='cache_key,updated_at,expires_at,'+','.join(p+':payload->'+p for p in paths)+',enabled:payload->enabled,status:payload->status,next_at:payload->next_at,active:payload->active'
 refs=store.db('GET','telegram_api_cache',params={'or':'('+','.join(clauses)+')','select':selected,'order':'cache_key','limit':500}) or []
 proof['remaining_old_cache_references']=refs
 check['cache_reference_scan_not_truncated']=len(refs)<500
 proof['old_target_advertising_jobs']=store.db('GET','advertising_agent_jobs',params={'chat_id':'eq.'+str(OLD),'select':'id,chat_id,status,origin','limit':100}) or []
 proof['old_target_advertising_watches']=store.db('GET','advertising_agent_watches',params={'chat_id':'eq.'+str(OLD),'select':'id,chat_id,status,next_check_at,expires_at','limit':100}) or []
 proof['old_target_business_jobs']=store.db('GET','business_agent_jobs',params={'chat_id':'eq.'+str(OLD),'select':'id,agent_id,chat_id,status,origin','limit':100}) or []
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
 proof['complete']=all(check.values())
except Exception as exc:proof.update(error_type=type(exc).__name__,error=str(exc)[:180])
seal('advertising-dialog-activation',proof)
print(json.dumps({k:proof.get(k) for k in ('complete','checks','source_calls','telegram_sends','wb_writes','configuration_writes','error')}))
if not proof['complete']:raise SystemExit(1)
