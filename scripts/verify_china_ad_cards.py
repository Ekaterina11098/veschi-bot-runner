"""Read existing private daily source only; never collect or deliver in this check."""
import json,hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
from china_price_apply import IO
from china_advertising_v2 import build
from china_advertising_cards import enhance
from china_advertising_v2_png import render
io=IO();day=datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()
s=io.get('china_agent:advertising_source:'+day+':v2')
if not s or s.get('status')!='complete':raise ValueError('No completed cached source for preview')
bundle=enhance(build(s),s);pages=render(bundle)
assert len(bundle['campaigns'])==len(s['ids'])
assert {p['family'] for p in pages}=={'drr','budgets'}
assert all(p['bytes'].startswith(b'\x89PNG') for p in pages)
audit=dict(status='verified',presentation=bundle['presentation'],day=day,campaigns=len(bundle['campaigns']),parts=[dict(kind=p['kind'],sha256=hashlib.sha256(p['bytes']).hexdigest()) for p in pages],wb_requests=0,wb_writes=0,telegram_sends=0)
key='china_agent:advertising_cards_v3:verification:'+day+':v1'
if io.get(key):io.put(key,audit)
else:assert io.create(key,audit)
print(json.dumps(dict(status='verified',wb_requests=0,wb_writes=0,telegram_sends=0)))
