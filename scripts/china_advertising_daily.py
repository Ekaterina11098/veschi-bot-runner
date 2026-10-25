"""China-only daily read/PNG/send with frozen daily artifacts and durable receipts."""
import os,json,base64,hashlib,tempfile
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from china_price_apply import IO
from china_advertising_collect import collect
from china_advertising_normalize import normalize
from china_advertising_png import render
from china_advertising_delivery import deliver,telegram_sender
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 day=datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat();io=IO()
 if (io.get('china_agent:advertising_delivery:'+day+':v1') or {}).get('status')=='delivered':
  print(json.dumps(dict(status='already_delivered',day=day,telegram_calls=0,wb_writes=0)));return
 key='china_agent:advertising_artifacts:'+day+':v2';saved=io.get(key)
 if not saved:
  from china_advertising_v2 import prepare,VERSION
  from china_advertising_v2_png import render as render_grouped
  from china_daily_ad_actions import plan
  bundle=prepare(io,day)
  pages=render_grouped(bundle);images=[]
  for index,f in enumerate(pages):
   p=plan(io,day,f,index)
   images.append(dict(kind=f['kind'],family=f['family'],page=f['page'],total=f['total'],plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],action_count=len(p['items']),b64=base64.b64encode(f['bytes']).decode()))
  saved=dict(day=day,status='frozen',bundle=bundle,files=images,wb_writes=0)
  if not io.create(key,saved):saved=io.get(key)
 if saved.get('day')!=day or saved.get('status')!='frozen':raise ValueError('Frozen image scope invalid')
 from china_daily_ad_actions import bind
 files=[]
 for f in saved['files']:
  caption='Китай · '+('реклама' if f['family']=='drr' else 'бюджеты')+' · '+day+' · '+str(f['page'])+'/'+str(f['total'])+'. Новых действий: '+str(f['action_count'])+'.'
  caption+=(' Ответьте «Сделай всё» для новых действий только этого PNG.' if f['action_count'] else ' Новых действий для исполнения нет.')
  files.append(dict(f,bytes=base64.b64decode(f['b64'],validate=True),caption=caption))
 result=deliver(io,day,files,telegram_sender(io),binder=lambda f,r:bind(io,f,r))
 print(json.dumps(dict(status=result['status'],day=day,message_ids=[x['message_id'] for x in result['parts']],wb_writes=0)))
if __name__=='__main__':run()

