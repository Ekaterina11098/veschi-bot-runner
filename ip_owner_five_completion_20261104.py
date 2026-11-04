"""One completion receipt for exact IP recovery run; no polling, WB access or retries."""
import os,json
from ip_apply_nine_20261103 import SixTransport,projection,stamp
from ip_daily_png_contract import digest
PLAN='ip_agent:owner_five:2026-11-04:v1'
EXEC=PLAN+':recovery:v2:execution'
EXPECTED_RUN='41887045933'
FROZEN='5688c35ccf0f2312bcad1fd3a205f35e7c0fdd57d99046b2e122a4192b2e43df'
CHAT=-1004378639510
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner':raise PermissionError('Public runner only')
 os.environ['WB_TOKEN_2']='NO_WB_PERMISSION';t=SixTransport();e=t.get(EXEC) or {};p=t.get(PLAN) or {}
 if e.get('status')!='verified' or str(e.get('run_id'))!=EXPECTED_RUN or digest(p.get('actions',[]))!=FROZEN or not e.get('readback_at'):return
 expected={(a['campaign'],a['nm']) for a in p['actions']}
 if len(e.get('items',[]))!=5 or {(i['campaign'],i['nm']) for i in e['items'] if i['status']=='verified'}!=expected or e.get('unrelated_members_settings_preserved')is not True:raise ValueError('Exact five-item final proof missing')
 if any(projection(e['after'][c])!=projection(e['expected'][c]) for c in e['expected']):raise ValueError('Final WB target mismatch')
 key=EXEC+':completion-notice'
 if not t.create(key,dict(status='sending',execution_key=EXEC,claimed_at=stamp())):return
 lines=['Выполнены все пять согласованных изменений ИП.']
 for a in p['actions']:
  if a['kind']=='remove':lines.append(a['sku']+' — исключён только из РК '+str(a['campaign'])+'.')
  else:lines.append(a['sku']+' · РК '+str(a['campaign'])+' — ставка '+format(a['target_bid_minor']/100,'.2f').replace('.',',')+' ₽.')
 lines.append('Результат каждого проверен чтением WB. Первые шесть изменений повторно не выполнялись.')
 try:
  token=os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()
  body=t.raw('https://api.telegram.org/bot'+token+'/sendMessage',{'Content-Type':'application/json'},'POST',dict(chat_id=CHAT,text='\n'.join(lines)))
  result=body.get('result') or {}
  if body.get('ok')is not True or result.get('chat',{}).get('id')!=CHAT or not result.get('message_id'):raise RuntimeError('Delivery not confirmed')
  t.save(key,dict(status='confirmed',message_id=result['message_id'],chat_id=CHAT,execution_key=EXEC,confirmed_at=stamp()))
 except Exception:t.save(key,dict(status='uncertain',execution_key=EXEC,blind_retry_allowed=False))
if __name__=='__main__':main()
