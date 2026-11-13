"""Owner13Nov audit of13 confirmed prices. Read-only, no Telegram."""
import json
from datetime import datetime,timezone
from china_advertising_state import AdvertisingIO
KEY='china_agent:price_execution:v1:-1004342917488:316:5122667182:0e8191b00c379784423bd8ea70dea738c0582c1010c46a07bee2c31457986342'
if __name__=='__main__':
 io=AdvertisingIO();e=io.get(KEY);assert e['status']=='done'and len(e['items'])==13
 ids=[x['request']['nmID']for x in e['items']]
 current=io.prices(ids);rows=[]
 for x in e['items']:
  nm=x['request']['nmID'];now=current[str(nm)]
  rows.append(dict(nm_id=nm,article=x['selection']['article'],approved=x['request'],verified=x.get('readback'),current=now,status=x['status']))
 value=dict(observed_at=datetime.now(timezone.utc).isoformat(),execution_key=KEY,rows=rows,wb_writes=0,telegram_calls=0)
 key='china_agent:owner_prices13_discount_audit:2026-11-13:v1:current'
 if not io.get(key):assert io.create(key,value)
 print(json.dumps(dict(status='audit_saved',products=len(rows),wb_writes=0)))
