"""One completion receipt for exact IP recovery run; no polling, WB access or retries."""
import os,json
from ip_apply_nine_20261103 import SixTransport,projection,stamp
from ip_daily_png_contract import digest
PLAN='ip_agent:png17:2026-11-05:v1'
EXEC=PLAN+':execution'
EXPECTED_RUN='41974599635'
FROZEN='b376d6869b9a3b52e64fb4689d72e045e7f24a644c56ae3e466f4ac7fee91f45'
CHAT=-1004378639510
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner':raise PermissionError('Public runner only')
 os.environ['WB_TOKEN_2']='NO_WB_PERMISSION';t=SixTransport();e=t.get(EXEC) or {};p=t.get(PLAN) or {}
 if e.get('status')!='verified' or str(e.get('run_id'))!=EXPECTED_RUN or digest(p.get('actions',[]))!=FROZEN or not e.get('readback_at'):return
 expected={(a['campaign'],a['nm']) for a in p['actions']}
 if len(e.get('items',[]))!=17 or {(i['campaign'],i['nm']) for i in e['items'] if i['status']=='verified'}!=expected or e.get('unrelated_members_settings_preserved')is not True:raise ValueError('Exact five-item final proof missing')
 if any(projection(e['after'][c])!=projection(e['expected'][c]) for c in e['expected']):raise ValueError('Final WB target mismatch')
 key=EXEC+':completion-notice'
 if not t.create(key,dict(status='sending',execution_key=EXEC,claimed_at=stamp())):return
 lines=['Выполнены все 17 согласованных изменений ИП из PNG за 5 ноября.']
 for a in p['actions']:
  if a['kind']=='remove':lines.append(a['sku']+' — исключён только из РК '+str(a['campaign'])+'.')
  else:lines.append(('Добавлен: ' if a['kind']=='add' else '')+a['sku']+' · РК '+str(a['campaign'])+' — ставка '+format(a['target_bid_minor']/100,'.2f').replace('.',',')+' ₽.')
 lines.append('Результат каждого проверен чтением WB. Бюджеты и остальные настройки не изменялись.')
 try:
  token=os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()
  body=t.raw('https://api.telegram.org/bot'+token+'/sendMessage',{'Content-Type':'application/json'},'POST',dict(chat_id=CHAT,text='\n'.join(lines)))
  result=body.get('result') or {}
  if body.get('ok')is not True or result.get('chat',{}).get('id')!=CHAT or not result.get('message_id'):raise RuntimeError('Delivery not confirmed')
  t.save(key,dict(status='confirmed',message_id=result['message_id'],chat_id=CHAT,execution_key=EXEC,confirmed_at=stamp()))
 except Exception:t.save(key,dict(status='uncertain',execution_key=EXEC,blind_retry_allowed=False))
if __name__=='__main__':main()
