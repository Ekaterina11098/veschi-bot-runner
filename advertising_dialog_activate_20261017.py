"""Read exact new-dialogue receipts and approved daily address; no processing or sending."""
import os,sys,json
sys.path.insert(0,'private-source')
from advertising_agent import agent_store as store
from stock_deploy_support import seal
r=store.registration()
jobs=store.db('GET','advertising_agent_jobs',params={'chat_id':'eq.'+str(r['chat_id']),'id':'gte.30','select':'id,update_id,chat_id,sender_id,request_text,reply_to_message_id,created_at,status,answer,tool_trace,delivery,error,attempts','order':'id.asc','limit':12}) or []
profiles={}
for key in ('advertising:ip:daily_rollout:v1','advertising:ip:limited_rollout:v1','advertising:dialog_rollout:v1'):
 p=store.cache_get(key) or {}
 profiles[key]={k:p.get(k) for k in ('enabled','chat_id','owner_id','source_sha','enabled_at','telegram_delivery_approved')}
proof=dict(complete=True,registration=r,jobs=jobs,profiles=profiles,source_calls=0,model_calls=0,telegram_sends=0,wb_writes=0)
seal('advertising-dialog-activation',proof)
print(json.dumps(dict(complete=True,read_jobs=len(jobs),source_calls=0,model_calls=0,telegram_sends=0,wb_writes=0)))
