"""Owner12Nov: audit all ready up/down recommendations, no price writes or paid calls."""
from datetime import date
from china_agent.morning_pair import PairWorker
def main():
 w=PairWorker('candidates')
 if w.day!=date(2026,11,12):raise RuntimeError('Dated review expired')
 try:
  w.run(preview=True)
  value=dict(status='verified_preview',answer=w.audit.get('preview'),audit=w.audit,model_calls=0,wb_writes=0,telegram_sends=0,grants_action_permission=False)
  w.save('china_agent:owner_price_complete:2026-11-12:v1:preview',value)
  print(dict(status=value['status'],model_calls=0,wb_writes=0))
 finally:
  import requests
  requests.sessions.Session.request=w.original_http
if __name__=='__main__':main()
