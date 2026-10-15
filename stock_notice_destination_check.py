import os,json,requests
from stock_deploy_support import seal,error,OUT
report={'success':False,'telegram_send_calls':0,'wb_calls':0,'old_queues_processed':0}
try:
 token=os.environ['TELEGRAM_BOT_TOKEN'].strip();chat=os.environ['TELEGRAM_ALLOWED_CHAT_ID'].strip()
 assert token and chat
 base='https://api.telegram.org/bot'+token
 def read(method,params=None):
  assert method in ('getMe','getChat','getChatMember')
  r=requests.get(base+'/'+method,params=params,timeout=(5,20),allow_redirects=False)
  if not r.ok:raise RuntimeError('Telegram read HTTP '+str(r.status_code))
  data=r.json()
  if data.get('ok') is not True:raise RuntimeError('Telegram read rejected')
  return data['result']
 me=read('getMe');assert me['is_bot'] is True
 info=read('getChat',{'chat_id':chat})
 assert str(info['id'])==chat
 member=read('getChatMember',{'chat_id':chat,'user_id':me['id']})
 assert member['status'] not in ('left','kicked')
 if member['status']=='restricted':assert member.get('can_send_messages') is True
 if info['type']=='channel':assert member['status']=='creator' or (member['status']=='administrator' and member.get('can_post_messages') is True)
 report.update(success=True,bot_identity=me,chat_identity=info,bot_membership=member,agreed_existing_secret_target_verified=True,delivery_not_tested=True)
except BaseException as exc:report['error']=error(exc)
finally:
 seal('stock-notice-destination',report)
 public={k:report[k] for k in ('success','telegram_send_calls','wb_calls','old_queues_processed')}
 if 'error' in report:public['error_type']=report['error']['type']
 (OUT/'notice-destination-summary.json').write_text(json.dumps(public))
 print(json.dumps(public))
raise SystemExit(0 if report['success'] else 1)
