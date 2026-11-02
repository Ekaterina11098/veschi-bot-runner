"""Owner-requested full OOO stock/COGS evidence; no WB/TG capabilities."""
import os,sys,time
from pathlib import Path
sys.path.insert(0,str(Path("private-source").resolve()))
from analytics.collect import database,snapshot
from china_moysklad_read import Reader,MoySkladReadError
import requests
CABINET="token_1"
cached=database("GET","analytics_snapshots",params={"source":"eq.ooo_api_full_msk","cabinet":"eq."+CABINET,"status":"eq.complete","collected_at":"gte.2026-11-02T00:00:00+03:00","select":"id","limit":1}) or []
if cached:print("Complete OOO scope already cached");sys.exit(0)
rows=database("GET","analytics_snapshots",params={"source":"eq.ooo_owner_prices","cabinet":"eq."+CABINET,"status":"eq.complete","select":"payload","order":"id.desc","limit":1}) or []
if not rows or not isinstance(rows[0]["payload"],list):raise RuntimeError("Private OOO article scope required")
articles=sorted({r["vendorCode"] for r in rows[0]["payload"]})
if len(articles)!=351:raise RuntimeError("OOO scope changed; review required")
def paced_get(*args,**kwargs):
    time.sleep(0.6)
    r=requests.get(*args,**kwargs)
    if r.status_code==429:raise MoySkladReadError("MoySklad HTTP 429; collection stopped without retry")
    return r
try:
    result=Reader(get=paced_get).stock(articles)
    result.update(cabinet=CABINET,requested_count=len(articles),price_minor_divisor=100,cost_currency_basis="RUB per existing MoySklad cost model; confirm against current user economics")
    snapshot("ooo_api_full_msk",CABINET,result,"complete" if result["coverage_complete"] else "partial")
    print("OOO stock/COGS saved privately; no WB, TG or commercial changes",flush=True)
except Exception as exc:
    snapshot("ooo_api_full_msk",CABINET,{"requested_count":len(articles)},"error",str(exc) if isinstance(exc,(MoySkladReadError,RuntimeError)) else type(exc).__name__)
    print("OOO stock source unavailable; see private evidence",flush=True)
