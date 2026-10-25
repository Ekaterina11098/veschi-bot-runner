"""Read-only predeployment preview. Never send Telegram or create action approvals."""
import base64,json,os
from datetime import datetime
from zoneinfo import ZoneInfo
from china_price_apply import IO
from china_advertising_v2 import prepare,save,VERSION
from china_advertising_v2_png import render
assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner'
io=IO();day=datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat();bundle=prepare(io,day);files=render(bundle);seen=set();images=[]
for f in files:
 if f['family'] not in seen:images.append(dict(kind=f['kind'],data=base64.b64encode(f['bytes']).decode()));seen.add(f['family'])
summary=dict(version=VERSION,status='verified_preview',day=day,campaigns=len(bundle['campaigns']),pages=len(files),ad_actions=sum(len(f['actions']) for f in files if f['family']=='drr'),budget_actions=sum(len(f['actions']) for f in files if f['family']=='budgets'),wb_writes=0,telegram_sends=0,images=images,bundle=bundle)
save(io,'china_agent:daily_format_v2_preview:'+day+':v1',summary)
print(json.dumps({k:v for k,v in summary.items() if k not in ['images','bundle']}))

