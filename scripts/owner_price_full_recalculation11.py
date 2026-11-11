"""Owner requested full price recalculation; no Telegram delivery or marketplace mutation."""
import json
from collections import Counter
from china_agent.coverage_worker import CoverageWorker
from china_agent.price_aggregate_control import build
from china_agent.price_brief import lowering
import requests
w=CoverageWorker('intraday')
try:
 w.control_preview=True
 w.prepare(preview=True)
 review=w.get('china_agent:daily_expected_candidates:'+str(w.day)+':verify')
 if not review:raise RuntimeError('Full recalculation receipt missing')
 omitted=[]
 ready=lowering(review,w.day,w.get('china_agent:prices:v1'),omitted=omitted)
 result=dict(status='calculated',report_date=str(w.day),review=review,lowering_ready=ready,omitted=omitted,source_cards_observed_at=w.audit.get('linked_cards_observed_at'),telegram_calls=0,wb_writes=0)
 w.save('china_agent:owner_price_full_recalculation:2026-11-11:v1',result)
 print(json.dumps(dict(status='calculated',products=len(review['products']),ready=len(ready or[]),unavailable=ready is None,omitted=len(omitted),result_states=dict(Counter((p.get('result')or{}).get('status',p.get('status'))for p in review['products'])),telegram_calls=0,wb_writes=0)))
finally:requests.sessions.Session.request=w.original_http
