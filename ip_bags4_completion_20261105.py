"""Exact-run completion receipt only. No WB access, no poll or blind resend."""
import os,json,hashlib
from ip_apply_nine_20261103 import SixTransport,stamp
PLAN='ip_agent:bags4:2026-11-05:v1';EXEC=PLAN+':execution'
def main():
 os.environ['WB_TOKEN_2']='NO_WB_PERMISSION';t=SixTransport();e=t.get(EXEC) or {};p=t.get(PLAN) or {}
 if e.get('status')!='verified' or str(e.get('run_id'))!='42028148609' or not e.get('readback_at'):return
 scope=p.get('scope',[])
 if hashlib.sha256(json.dumps(scope,sort_keys=True,separators=(',',':')).encode()).hexdigest()!='163b0f2f3a0591021110f2777ba9ea35c91f3d885e249d574de9d62f354a9e7e':raise ValueError('Wrong3scope')
 if e.get('unrelated_members_settings_preserved')is not True or len(e.get('items',[]))!=4 or any(i['status']!='verified' for i in e['items']):raise ValueError('No final3proof')
 for a in scope:
  n=next(n for n in e['after']['39483230']['nm_settings'] if n['nm_id']==a['nm'])
  if n['bids_kopecks']['search']!=295:raise ValueError('Wrongtarget')
 key=EXEC+':completion-notice'
 if not t.create(key,dict(status='sending',claimed_at=stamp())):return
 try:
  text='В РК 39483230 добавлены по 2,95 ₽ за клик:\n'+ '\n'.join(a['sku'] for a in scope)+'\nСостав и ставки подтверждены чтением WB. Остальные товары и прежние изменения не повторялись. Пополнений не выполнялось.'
  token=os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()
  r=t.raw('https://api.telegram.org/bot'+token+'/sendMessage',{'Content-Type':'application/json'},'POST',dict(chat_id=-1004378639510,text=text))
  result=r.get('result') or {}
  if r.get('ok')is not True or result.get('chat',{}).get('id')!=-1004378639510 or not result.get('message_id'):raise ValueError('Unknown delivery')
  t.save(key,dict(status='confirmed',message_id=result['message_id'],confirmed_at=stamp()))
 except Exception:t.save(key,dict(status='uncertain',blind_retry_allowed=False))
if __name__=='__main__':main()
