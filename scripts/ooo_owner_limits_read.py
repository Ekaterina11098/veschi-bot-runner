"""OOO read-only bid limits and budget evidence, no commercial changes."""
import os,sys,time
from pathlib import Path
sys.path.insert(0,str(Path("private-source").resolve()))
from analytics.collect import database,snapshot,fetch
CABINET="token_1"
TOKEN=os.environ["WB_TOKEN_1"]
rows=database("GET","analytics_snapshots",params={"source":"eq.ooo_owner_configuration","cabinet":"eq."+CABINET,"status":"eq.complete","select":"payload","order":"id.desc","limit":1}) or []
if not rows:raise RuntimeError("Private OOO configuration required")
adverts=rows[0]["payload"]["adverts"]
def read(source,path,body=None):
    method="POST" if body is not None else "GET"
    allowed={("GET","/api/advert/v1/config"),("POST","/api/advert/v2/budget"),("POST","/api/advert/v1/bids/min")}
    if (method,path) not in allowed:raise RuntimeError("Read-only boundary")
    try:
        time.sleep(1.5)
        value=fetch(method,"https://advert-api.wildberries.ru"+path,TOKEN,body=body,max_retry_wait=0)
        snapshot(source,CABINET,{"request":body,"data":value})
    except Exception as exc:
        snapshot(source,CABINET,{"request":body},"error",str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__)
read("ooo_api_ad_config","/api/advert/v1/config")
read("ooo_api_budgets","/api/advert/v2/budget",{"advertIds":[a["id"] for a in adverts]})
for a in adverts:
    zones=[]
    placements=a["settings"]["placements"]
    if placements.get("search"):zones.append("search")
    if placements.get("recommendations"):zones.append("recommendation")
    read("ooo_api_minimums","/api/advert/v1/bids/min",{"advert_id":a["id"],"nm_ids":[n["nm_id"] for n in a["nm_settings"]],"payment_type":a["settings"]["payment_type"],"placement_types":zones})
print("OOO limits read finished; private evidence only",flush=True)
