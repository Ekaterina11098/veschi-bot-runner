"""Read-only OOO Telegram identity diagnostic; persist metadata only, no messages/models."""
import os,json
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from ooo_sol_dialog import DB,ROOT,BOT,CHAT
from bounded_sol_dialog import stamp,dump

def tg(method,body=None):
 url='https://api.telegram.org/bot'+os.environ['OOO_TELEGRAM_BOT_TOKEN'].strip()+'/'+method
 try:
  with urlopen(Request(url,data=dump(body or{}).encode(),headers={'Content-Type':'application/json'}),timeout=35)as r:return json.load(r)
 except HTTPError as e:
  try:
   value=json.load(e)
   return {'ok':False,'error_code':value.get('error_code'),'parameters':value.get('parameters')}
  except Exception:return {'ok':False,'error_code':e.code}

def main():
 db=DB();bot=(tg('getMe').get('result')or{})
 if bot.get('id')!=BOT:raise PermissionError('Wrong bot')
 chat=tg('getChat',{'chat_id':CHAT});info=chat.get('result')or{}
 admins=tg('getChatAdministrators',{'chat_id':CHAT}).get('result')or[]
 updates=tg('getUpdates',{'limit':100,'timeout':0,'allowed_updates':['message','callback_query','my_chat_member']})
 candidates={}
 migrations=[]
 for u in updates.get('result')or[]:
  m=u.get('message')or(u.get('callback_query')or{}).get('message')or u.get('my_chat_member')or{}
  c=m.get('chat')or{}
  if c.get('type')not in('group','supergroup'):continue
  cid=c['id']
  if cid not in candidates:
   status=(tg('getChatMember',{'chat_id':cid,'user_id':BOT}).get('result')or{}).get('status')
   owner=(tg('getChatMember',{'chat_id':cid,'user_id':5122667182}).get('result')or{}).get('status')
   candidates[cid]={'chat_id':cid,'title':c.get('title'),'type':c.get('type'),'bot_status':status,'owner_status':owner}
  if m.get('migrate_to_chat_id')or m.get('migrate_from_chat_id'):migrations.append({k:m.get(k)for k in('migrate_to_chat_id','migrate_from_chat_id')}|{'chat_id':cid})
 result={'observed_at':stamp(),'run_id':os.environ.get('GITHUB_RUN_ID'),'bot_id':BOT,'username':bot.get('username'),'configured_chat':{k:info.get(k)for k in('id','title','type')},'configured_chat_error':chat.get('parameters'),'configured_bot_in_admin_list':any(a.get('user',{}).get('id')==BOT for a in admins),'visible_pending_chats':list(candidates.values()),'migrations':migrations,'updates_read_only':True,'updates_acknowledged':False,'messages_sent':0,'model_calls':0}
 db.put(ROOT+'identity_diagnostic',result)
 print(dump(result))
if __name__=='__main__':main()
