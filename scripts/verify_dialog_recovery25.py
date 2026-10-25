import base64,json
from china_price_apply import IO
from china_advertising_intraday import prepare
from china_advertising_v2_png import render
io=IO();b=prepare(io,'2026-10-25');files=render(b)
key='china_agent:dialog_recovery_preview:2026-10-25:v1'
p=dict(status='verified_preview',bundle=b,parts=[dict(family=x['family'],base64=base64.b64encode(x['bytes']).decode()) for x in files],wb_writes=0,telegram_sends=0)
if io.get(key):io.put(key,p)
else:assert io.create(key,p)
print(json.dumps(dict(status='verified_preview',campaigns=len(b['campaigns']),pages=len(files),wb_writes=0,telegram_sends=0)))
