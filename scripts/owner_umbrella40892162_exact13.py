"""Resolve exact current seller prices only; zero marketplace mutations."""
import json
from datetime import datetime,timezone
from china_advertising_state import AdvertisingIO
if __name__=='__main__':
 io=AdvertisingIO()
 rows=io.prices([1556488181,1556488209,1556488210])
 key='china_agent:owner_umbrella40892162:2026-11-13:v1:exact_prices'
 value=dict(observed_at=datetime.now(timezone.utc).isoformat(),rows=rows,wb_writes=0,telegram_calls=0)
 if not io.get(key):assert io.create(key,value)
 print(json.dumps(dict(status='exact_prices_saved',prices={nm:[s['discountedPrice']for s in r['sizes']]for nm,r in rows.items()})))
