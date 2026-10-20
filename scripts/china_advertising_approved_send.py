import base64,json
from datetime import datetime
from zoneinfo import ZoneInfo
from china_price_apply import IO
from china_advertising_delivery import deliver,telegram_sender
day=datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()
if day!='2026-10-20':raise ValueError('Expired approved delivery')
io=IO();p=io.get('china_agent:advertising_approved_png:2026-10-20:v1')
if not p or p['status']!='approved' or p['report_day']!=day:raise ValueError('Missing owner-approved images')
files=[dict(kind=f['kind'],bytes=base64.b64decode(f['b64'],validate=True),caption=('Китай · ДРР и расходы за 19.10.2026 / 13–19.10.2026' if f['kind']=='drr' else 'Китай · бюджеты · проверка 20.10.2026 18:07–18:08 МСК')) for f in p['files']]
for f,source in zip(files,p['files']):
 if len(f['bytes'])!=source['bytes']:raise ValueError('PNG integrity mismatch')
result=deliver(io,day,files,telegram_sender(io))
print(json.dumps(dict(status=result['status'],message_ids=[x['message_id'] for x in result['parts']],wb_writes=0)))
