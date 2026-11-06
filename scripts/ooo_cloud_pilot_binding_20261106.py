"""Read-only diagnosis of the exact failed pilot binding, no model or sends."""
import os,json,datetime,requests
from china_codex_cloud import DB,stamp
ROOT='ooo_agent:cloud_pilot:2026-11-06:v1'
db=DB();old=db.get(ROOT+':execution')or{};auth=db.get(ROOT+':authorization')or{}
if old.get('status')!='attention'or old.get('safe_error')!='Expected one authorized pilot group command'or old.get('model_calls')!=0:raise SystemExit('No matching uncharged binding failure')
if db.get(ROOT+':binding_diagnostic'):raise SystemExit('Existing diagnostic retained')
token=os.environ['OOO_TELEGRAM_BOT_TOKEN'].strip()
r=requests.post('https://api.telegram.org/bot'+token+'/getUpdates',data={'limit':20,'timeout':0,'allowed_updates':json.dumps(['message'])},timeout=(10,30),allow_redirects=False)
if r.status_code!=200:raise SystemExit('Telegram diagnostic read rejected')
j=r.json()
if not j.get('ok'):raise SystemExit('Telegram diagnostic read not acknowledged')
rows=[]
for u in j['result']:
 m=u.get('message')or{};text=m.get('text','').strip();chat=m.get('chat')or{};sender=m.get('from')or{}
 if not text.casefold().startswith(('/pilot','/start')):continue
 rows.append({'chat_id':chat.get('id'),'chat_title':chat.get('title'),'chat_type':chat.get('type'),'sender_id':sender.get('id'),'sender_is_bot':sender.get('is_bot'),'has_sender_chat':bool(m.get('sender_chat')),'message_id':m.get('message_id'),'date':m.get('date'),'command_kind':'exact'if text.casefold()==('/pilot@'+auth['expected_username']).casefold()else'bare_pilot'if text.casefold()=='/pilot'else'other_command','command_length':len(text)})
db.once(ROOT+':binding_diagnostic',{'status':'complete','observed_at':stamp(),'messages_received':len(j['result']),'command_metadata':rows,'model_calls':0,'telegram_sends':0})
print('Scoped binding metadata saved privately; no model or sends')
