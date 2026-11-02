"""Owner-requested OOO advertising evidence; no marketplace mutations or delivery."""
import os,sys,time
from pathlib import Path
sys.path.insert(0,str(Path("private-source").resolve()))
from analytics.collect import fetch as source_fetch,database,snapshot,cards,identity
from analytics.wb_sources import collect
from datetime import datetime
from zoneinfo import ZoneInfo
CABINET="token_1"
TOKEN=os.environ["WB_TOKEN_1"]
ALLOWED_GET={
"https://common-api.wildberries.ru/api/v1/seller-info",
"https://advert-api.wildberries.ru/adv/v1/upd",
"https://advert-api.wildberries.ru/adv/v1/promotion/count",
"https://advert-api.wildberries.ru/adv/v3/fullstats",
"https://advert-api.wildberries.ru/api/advert/v2/adverts",
"https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter",
}
def read(method,url,token,params=None,body=None,max_retry_wait=0):
    if token!=TOKEN:raise RuntimeError("Cabinet boundary rejected")
    allowed=(method=="GET" and url in ALLOWED_GET) or (method=="POST" and url=="https://content-api.wildberries.ru/content/v2/get/cards/list")
    if not allowed:raise RuntimeError("Read-only endpoint boundary rejected")
    return source_fetch(method,url,token,params=params,body=body,max_retry_wait=0)
import analytics.collect as core
core.fetch=read
def attempt(source,fn):
    try:fn()
    except Exception as exc:
        detail=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
        snapshot(source,CABINET,None,"error",detail)
        print(source,"unavailable",flush=True)
attempt("seller_identity",lambda:identity(CABINET,TOKEN))
attempt("cards",lambda:cards(CABINET,TOKEN))
collect(CABINET,read,database,include_funnel=False)
def configuration():
    rows=database("GET","analytics_snapshots",params={"source":"eq.advertising_campaign_index","cabinet":"eq."+CABINET,"status":"eq.complete","select":"payload,collected_at","order":"collected_at.desc","limit":1}) or []
    if not rows:raise RuntimeError("Campaign index unavailable")
    stamp=datetime.fromisoformat(rows[0]["collected_at"].replace("Z","+00:00"))
    if (datetime.now(ZoneInfo("UTC"))-stamp).total_seconds()>3600:raise RuntimeError("Campaign index stale")
    raw=rows[0]["payload"]["raw"]
    ids=sorted({int(a["advertId"]) for group in raw["adverts"] if group.get("status") in (4,9,11) for a in group.get("advert_list",[])})
    adverts=[]
    for offset in range(0,len(ids),50):
        if offset:time.sleep(1)
        data=read("GET","https://advert-api.wildberries.ru/api/advert/v2/adverts",TOKEN,params={"ids":",".join(map(str,ids[offset:offset+50]))})
        if not isinstance(data,dict) or not isinstance(data.get("adverts"),list):raise RuntimeError("Configuration schema invalid")
        adverts.extend(data["adverts"])
    missing=sorted(set(ids)-{int(a["id"]) for a in adverts})
    snapshot("ooo_owner_configuration",CABINET,{"requested_ids":ids,"missing_ids":missing,"adverts":adverts},"partial" if missing else "complete")
attempt("ooo_owner_configuration",configuration)
def prices():
    offset=0
    for page in range(100):
        data=read("GET","https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter",TOKEN,params={"limit":1000,"offset":offset})
        rows=(data.get("data") or {}).get("listGoods")
        if not isinstance(rows,list):raise RuntimeError("Price schema invalid")
        snapshot("ooo_owner_prices",CABINET,rows,"page" if len(rows)==1000 else "complete")
        if len(rows)<1000:return
        offset+=len(rows)
        time.sleep(1)
    raise RuntimeError("Price pagination incomplete")
attempt("ooo_owner_prices",prices)
print("OOO read-only evidence collection finished; consult private snapshot status",flush=True)
