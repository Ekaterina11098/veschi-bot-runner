"""Delete only the exact superseded Telegram message authorized by the user."""
import os,json
from datetime import datetime,timezone
import requests
from conversion_watches import runtime
KEY='china_agent:approved_delete:173:keep175:v1'
def main():
 w=runtime();old=w.get('china_agent:advertising_delivery:2026-10-24:v1');new=w.get('china_agent:approved_553_delivery:2026-10-24:v1')
 assert new['delivery_status']=='sent' and new['message_id']==175 and new['chat_id']==-1004342917488
 part=next(x for x in old['parts'] if x['message_id']==173)
 assert part['receipt']['chat']['id']==-1004342917488 and part['receipt']['from']['id']==8780468043
 p=w.get(KEY) or dict(status='ready',message_id=173,preserve_message_id=175,chat_id=-1004342917488)
 if p['status']=='deleted':print(json.dumps(dict(status='already_deleted',message_id=173,preserved=175)));return
 if p['status'] in ('deleting','uncertain'):raise SystemExit('Uncertain deletion: investigate')
 def tg(method,body):return requests.post('https://api.telegram.org/bot'+os.environ['CHINA_TELEGRAM_BOT_TOKEN'].strip()+'/'+method,json=body,timeout=40).json()
 me=tg('getMe',{})
 assert me.get('ok') and me['result']['id']==8780468043
 p.update(status='deleting',started_at=datetime.now(timezone.utc).isoformat());w.save(KEY,p)
 try:r=tg('deleteMessage',dict(chat_id=p['chat_id'],message_id=173))
 except Exception:
  p['status']='uncertain';w.save(KEY,p);raise SystemExit('Delete result uncertain')
 if not r.get('ok'):
  p.update(status='rejected',error_code=r.get('error_code'));w.save(KEY,p);raise SystemExit('Delete rejected')
 p.update(status='deleted',deleted_at=datetime.now(timezone.utc).isoformat(),telegram_result=r['result']);w.save(KEY,p)
 part.update(deleted_by_human_request=True,deleted_at=p['deleted_at'],deletion_receipt_key=KEY)
 w.save('china_agent:advertising_delivery:2026-10-24:v1',old)
 assert w.get('china_agent:approved_553_delivery:2026-10-24:v1')['message_id']==175
 print(json.dumps(dict(status='deleted',message_id=173,preserved=175,wb_writes=0,telegram_sends=0)))
if __name__=='__main__':
 assert os.environ.get('GITHUB_REPOSITORY')=='Ekaterina11098/veschi-bot-runner'
 main()
