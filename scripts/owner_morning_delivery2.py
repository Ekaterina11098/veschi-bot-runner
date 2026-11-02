"""Owner-authorized frozen daily delivery waits in cloud; no marketplace reads or writes."""
import time
from datetime import datetime,timezone
from china_cloud_cost_control import Cache
from china_advertising_daily import run
DAY="2026-11-02"
def main():
 c=Cache()
 for attempt in range(90):
  auth=c.get("china_agent:advertising_manual_delivery:"+DAY+":v1")or{}
  if auth.get("owner_user_id")!=5122667182 or auth.get("authorized")is not True or datetime.now(timezone.utc)>=datetime.fromisoformat(auth["expires_at"]):raise ValueError("Manual delivery authorization absent/expired")
  if (c.get("china_agent:advertising_delivery:"+DAY+":v1")or{}).get("status")=="delivered":return
  artifacts=c.get("china_agent:advertising_artifacts:"+DAY+":v2")or{}
  if artifacts.get("status")=="frozen"and artifacts.get("day")==DAY:
   source=c.get("china_agent:advertising_source:"+DAY+":v2")or{}
   if (source.get("day_quality")or{}).get("usable")is not True:raise ValueError("Daily quality unconfirmed")
   run();return
  time.sleep(10)
 raise RuntimeError("Frozen daily report preparation not completed; no Telegram send")
if __name__=="__main__":main()
