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
 key='china_agent:advertising_artifacts:'+day+':v1';saved=io.get(key)
 if not saved:
  source=collect(io,day)
  prices=io.get('china_agent:prices:v1') or {}
  if prices.get('cabinet')!='token_3':raise ValueError('China article catalogue unavailable')
  articles={str(x['nmID']):x['vendorCode'] for x in prices.get('rows',[])}
  # Reuse complete archived daily campaign summaries; no extra MPStats calls.
  history=[io.get('china_agent:advertising_source:'+(datetime.fromisoformat(day).date()-timedelta(days=i)).isoformat()+':v1') or {} for i in (1,2)]
  bundle=normalize(source,day,articles,history)
  with tempfile.TemporaryDirectory() as out:
   paths=render(bundle,out)
   images=[dict(kind=k,b64=base64.b64encode(p.read_bytes()).decode()) for k,p in zip(('drr','budgets'),paths)]
  saved=dict(day=day,status='frozen',bundle=bundle,files=images,wb_writes=0)
  if not io.create(key,saved):saved=io.get(key)
 if saved.get('day')!=day or saved.get('status')!='frozen':raise ValueError('Frozen image scope invalid')
 files=[dict(kind=f['kind'],bytes=base64.b64decode(f['b64'],validate=True),
  caption=('Китай · ДРР и расходы за '+saved['bundle']['period'] if f['kind']=='drr' else 'Китай · бюджеты · '+day+' · время проверки внутри')) for f in saved['files']]
 result=deliver(io,day,files,telegram_sender(io))
 print(json.dumps(dict(status=result['status'],day=day,message_ids=[x['message_id'] for x in result['parts']],wb_writes=0)))
if __name__=='__main__':run()
