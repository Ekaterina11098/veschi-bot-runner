"""Owner-authorized exact reply to Pavel job40 only. No WB or model access."""
import os,json,uuid,datetime,urllib.parse
from ip_apply_nine_20261103 import SixTransport,stamp
KEY='ip_agent:pavel:job40:2026-11-05:reply:v1'
def main():
 os.environ['WB_TOKEN_2']='NO_WB_PERMISSION';t=SixTransport();p=t.get(KEY)
 if not p or p['job_id']!=40 or p['chat_id']!=-1004378639510 or p['reply_to_message_id']!=60:raise PermissionError('Exact reply missing')
 claim=KEY+':delivery'
 if t.get(claim):return
 q=urllib.parse.urlencode(dict(id='eq.40',chat_id='eq.-1004378639510',sender_id='eq.307200273',status='eq.pending'))
 lease=str(uuid.uuid4());h=dict(t.sh,Prefer='return=representation')
 r=t.raw(t.sb+'/rest/v1/advertising_agent_jobs?'+q,h,'PATCH',dict(status='running',lease_token=lease,lease_until=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=15)).isoformat(),answer=p['text']))
 if len(r)!=1:raise PermissionError('Job already taken/answered; no duplicate')
 if not t.create(claim,dict(status='sending',job_id=40,claimed_at=stamp())):return
 try:
  token=os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()
  result=t.raw('https://api.telegram.org/bot'+token+'/sendMessage',{'Content-Type':'application/json'},'POST',dict(chat_id=p['chat_id'],text=p['text'],reply_parameters=dict(message_id=60,allow_sending_without_reply=False)))
  msg=result.get('result') or {}
  if result.get('ok')is not True or msg.get('chat',{}).get('id')!=p['chat_id'] or not msg.get('message_id'):raise ValueError('Unknown delivery')
  delivery=dict(status='confirmed',message_id=msg['message_id'],chat_id=p['chat_id'],reply_to_message_id=60,confirmed_at=stamp())
  t.save(claim,delivery)
  q=urllib.parse.urlencode(dict(id='eq.40',lease_token='eq.'+lease))
  t.raw(t.sb+'/rest/v1/advertising_agent_jobs?'+q,t.sh,'PATCH',dict(status='done',completed_at=stamp(),lease_until=None,answer=p['text'],delivery=dict(route='owner-authorized-exact-reply',send_state='confirmed',answer_message_id=msg['message_id'],incoming_message_id=60,receipt_at=stamp())))
 except Exception:
  t.save(claim,dict(status='uncertain',job_id=40,blind_retry_allowed=False))
  raise RuntimeError('Reply delivery unknown; do not resend') from None
if __name__=='__main__':main()
