import os,sys,json
from pathlib import Path
import requests
sys.path.insert(0,'private-source')
from advertising_agent import agent_store as store
from stock_deploy_support import seal
p={'model_calls':0,'source_calls':0,'wb_writes':0,'telegram_sends':0}
try:
 r=store.registration();token=os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()
 def tg(name,params=None):
  x=requests.get('https://api.telegram.org/bot'+token+'/'+name,params=params,timeout=(5,20));v=x.json()
  if not x.ok or not v.get('ok'):raise RuntimeError('Telegram identity check failed')
  return v['result']
 me=tg('getMe');member=tg('getChatMember',{'chat_id':r['chat_id'],'user_id':me['id']});info=tg('getWebhookInfo')
 p.update(bot_username=me['username'],can_read_all_group_messages=me.get('can_read_all_group_messages',False),
  bot_membership=member.get('status'),registered_chat=r['chat_id'],owner_id=r['registered_by_user_id'],
  group_text_delivery_ready=bool(me.get('can_read_all_group_messages')) or member.get('status') in ('administrator','creator'),
  webhook_url=info.get('url'),pending_update_count=info.get('pending_update_count'),last_error=info.get('last_error_message'),
  openai_key_present=bool(os.environ.get('OPENAI_API_KEY','').strip()),model=os.environ.get('ADVERTISING_AI_MODEL') or 'gpt-4o-mini')
 state=store.cache_get('advertising:agent_webhook') or {}
 p['webhook_config_keys']=list(state)
 p['jobs']=store.db('GET','advertising_agent_jobs',params={'chat_id':'eq.'+str(r['chat_id']),'select':'id,origin,status,created_at','order':'id.desc','limit':5}) or []
 p['saved_analysis']=store.db('GET','analytics_snapshots',params={'source':'eq.ip_working_mode_replay','cabinet':'eq.token_2','select':'id,period_from,period_to,collected_at','order':'id.desc','limit':2}) or []
 p['complete']=True
except Exception as e:p.update(complete=False,error_type=type(e).__name__,error=str(e)[:100])
seal('advertising-chat-preflight',p)
print(json.dumps({k:p.get(k) for k in ('complete','openai_key_present','group_text_delivery_ready','model_calls','telegram_sends','source_calls','wb_writes','error_type')}))
if not p.get('complete'):raise SystemExit(1)
