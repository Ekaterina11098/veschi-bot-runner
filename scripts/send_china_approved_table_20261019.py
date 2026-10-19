"""Single owner-requested preview of the saved 19 October morning report."""
import os,json,hashlib
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import requests
from china_price_brief import render_table,table_payload
from china_buyer_price_forecast import build
import sys,types,china_buyer_price_forecast
sys.modules['china_agent']=types.ModuleType('china_agent')
sys.modules['china_agent.buyer_price_forecast']=china_buyer_price_forecast
CHAT=-1004342917488
KEY='china_agent:approved_price_table:2026-10-19:v1'
BASE=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/'
SECRET=os.environ['SUPABASE_SECRET_KEY']
HEAD={'apikey':SECRET,'Authorization':'Bearer '+SECRET}
def db(method,table,**kwargs):
 r=requests.request(method,BASE+table,headers=HEAD,timeout=40,**kwargs)
 r.raise_for_status()
 return r.json() if r.content else None
def telegram(method,body):
 r=requests.post('https://api.telegram.org/bot'+os.environ['CHINA_TELEGRAM_BOT_TOKEN']+'/'+method,json=body,timeout=40)
 # Never print response URLs or token-bearing exceptions.
 try:value=r.json()
 except Exception:raise RuntimeError('Telegram response not JSON') from None
 if not r.ok or not value.get('ok'):raise RuntimeError('Telegram request not confirmed') from None
 return value['result']
def main():
 day=datetime.now(ZoneInfo('Europe/Moscow')).date()
 if str(day)!='2026-10-19':raise RuntimeError('Preview date expired')
 old=db('GET','telegram_api_cache',params=dict(cache_key='eq.'+KEY,select='payload'))
 if old:
  print(json.dumps(dict(status=old[0]['payload']['status'],already_recorded=True)))
  return
 jobs=db('GET','business_agent_jobs',params=dict(id='eq.51',agent_id='eq.china',select='id,status,chat_id,request_text,answer,created_at'))
 if len(jobs)!=1:raise RuntimeError('Saved report missing')
 job=jobs[0]
 if job['status']!='done' or job['chat_id']!=CHAT or job['request_text']!='/china_morning_pair_candidates' or not job['created_at'].startswith(str(day)):raise RuntimeError('Saved report scope mismatch')
 review=db('GET','telegram_api_cache',params=dict(cache_key='eq.china_agent:daily_expected_candidates:'+str(day),select='payload'))
 value=review[0]['payload'] if len(review)==1 else None
 catalogue=db('GET','telegram_api_cache',params=dict(cache_key='eq.china_agent:prices:v1',select='payload'))
 if len(catalogue)!=1:raise RuntimeError('Catalogue missing')
 original=db('GET','telegram_api_cache',params=dict(cache_key='eq.china_agent:brief_owner_preview:2026-10-19:v1',select='payload'))
 if len(original)!=1 or original[0]['payload'].get('status')!='sent' or original[0]['payload'].get('message_id')!=47 or original[0]['payload'].get('chat_id')!=CHAT:
  raise RuntimeError('Original message receipt mismatch')
 snapshots=db('GET','analytics_snapshots',params=dict(id='eq.18445',cabinet='eq.token_3',source='eq.mpstats_lk_wb_products',status='eq.complete',select='id,payload,collected_at,period_from,period_to'))
 if len(snapshots)!=1:raise RuntimeError('Buyer price source missing')
 marker=snapshots[0]
 observation,=marker['payload']
 args=observation['arguments'];body=observation['data']['data'];rows=body['data']
 if observation.get('scope_verified') is not True or observation.get('status')!='received' or args.get('date_from')!='2026-10-18' or args.get('date_to')!='2026-10-18' or args.get('start_row')!=0 or body.get('need_update')!=0 or body.get('total')!=len(rows):
  raise RuntimeError('Buyer price source unverified')
 buyer=build(rows,marker,catalogue[0]['payload'],day)
 text=render_table(job['answer'],'morning',value,day,catalogue[0]['payload'],buyer)
 text=text.replace('Действие','Рекомендация',1)
 if any(str(amount) not in text.replace(' ','') for amount in (947,2156,4086,892)):raise RuntimeError('Approved forecast differs')
 payload=table_payload(text,catalogue[0]['payload'])
 if not payload or len(payload['entities'])!=5:raise RuntimeError('Product links incomplete')
 if len(text)>3400:raise RuntimeError('Preview requires more than one part')
 if telegram('getMe',{})['id']!=8780468043:raise RuntimeError('Bot identity mismatch')
 if telegram('getChat',{'chat_id':CHAT})['id']!=CHAT:raise RuntimeError('Chat identity mismatch')
 receipt=dict(status='sending',buyer_snapshot_id=18445,template_approved=True,job_id=51,chat_id=CHAT,report_date=str(day),answer=text,sha256=hashlib.sha256(text.encode()).hexdigest(),started_at=datetime.now(timezone.utc).isoformat(),wb_writes=0)
 # Plain insert: a duplicate key prevents a second send, including concurrent runs.
 db('POST','telegram_api_cache',json=dict(cache_key=KEY,payload=receipt,expires_at='2036-10-19T00:00:00Z'))
 saved=db('GET','telegram_api_cache',params=dict(cache_key='eq.'+KEY,select='payload'))
 if len(saved)!=1 or saved[0]['payload']!=receipt:raise RuntimeError('Reservation readback mismatch')
 try:
  result=telegram('sendMessage',dict(chat_id=CHAT,text=text,**payload))
 except Exception:
  receipt.update(status='uncertain',finished_at=datetime.now(timezone.utc).isoformat())
  db('PATCH','telegram_api_cache',params=dict(cache_key='eq.'+KEY),json=dict(payload=receipt))
  raise RuntimeError('Delivery uncertain; do not resend') from None
 receipt.update(status='sent',entities=result.get('entities',[]),message_id=result['message_id'],telegram_date=result['date'],finished_at=datetime.now(timezone.utc).isoformat())
 if result['chat']['id']!=CHAT:raise RuntimeError('Confirmed response chat mismatch')
 db('PATCH','telegram_api_cache',params=dict(cache_key='eq.'+KEY),json=dict(payload=receipt))
 check=db('GET','telegram_api_cache',params=dict(cache_key='eq.'+KEY,select='payload'))
 if len(check)!=1 or check[0]['payload']!=receipt:raise RuntimeError('Receipt readback mismatch')
 print(json.dumps(dict(status='sent',message_id=receipt['message_id'],chat_id=CHAT,new_messages=1,wb_writes=0)))
if __name__=='__main__':
 try:main()
 except Exception as exc:
  # requests exceptions can contain secret-bearing URLs.
  print(json.dumps(dict(status='failed',error_type=type(exc).__name__)))
  raise SystemExit(1)
