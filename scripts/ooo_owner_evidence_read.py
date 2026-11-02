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
def campaign_index():
    raw=read("GET","https://advert-api.wildberries.ru/adv/v1/promotion/count",TOKEN)
    if not isinstance(raw,dict) or not isinstance(raw.get("adverts"),list):raise RuntimeError("Index schema invalid")
    snapshot("advertising_campaign_index",CABINET,{"raw":raw,"campaign_ids":sorted({int(a["advertId"]) for g in raw["adverts"] for a in g.get("advert_list",[])})})
attempt("advertising_campaign_index",campaign_index)
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

from analytics.mpstats_probe import discover,unpack_tool,sanitize,complete_products
from datetime import timedelta
END=datetime.now(ZoneInfo("Europe/Moscow")).date()-timedelta(days=1)
START=END-timedelta(days=27)
def extra(call,checks,seen):
    def tool(name,args):
        allowed={"lk_wb_cabinets","lk_wb_products","wbbidder_cabinets","wbbidder_campaigns","wbbidder_campaign_stats"}
        if name not in allowed:raise RuntimeError("MPStats read boundary rejected")
        return sanitize(unpack_tool(call("tools/call",{"name":name,"arguments":args})))
    cabinets=tool("wbbidder_cabinets",{})
    matched=[r for r in cabinets.get("data",[]) if r.get("id")==913194 and r.get("name")=="Киргизия VESCHI"]
    if len(matched)!=1:raise RuntimeError("OOO bidder identity unverified")
    def save(source,value,args):
        snapshot(source,CABINET,{"data":value,"arguments":args,"observed_at":datetime.now(ZoneInfo("UTC")).isoformat()},period_from=START,period_to=END)
    save("ooo_api_bidder_identity",matched,{})
    ids=set()
    for offset in range(0,1000,100):
        args={"tokens":[913194],"d1":str(START),"d2":str(END),"report":"stats","limit":100,"start_row":offset}
        value=tool("wbbidder_campaigns",args)
        save("ooo_api_campaign_catalog",value,args)
        rows=value.get("data")
        if not isinstance(rows,list):raise RuntimeError("Campaign catalog schema invalid")
        for row in rows:
            cid=row.get("id") or row.get("advertId") or row.get("campaign_id")
            if cid:ids.add(int(cid))
        if len(rows)<100:break
    else:raise RuntimeError("Campaign catalog pagination incomplete")
    for cid in sorted(ids)[:60]:
        for report in ("days","products"):
            args={"campaign_id":cid,"d1":str(START),"d2":str(END),"report":report,"zone":"all"}
            value=tool("wbbidder_campaign_stats",args)
            save("ooo_api_campaign_"+report,value,args)
    cabinets=checks["lk_wb_cabinets"]
    matches=[r for r in cabinets if r.get("id")==10014167 and r.get("name")=="Киргизия VESCHI" and r.get("valid") is True]
    if len(matches)!=1:raise RuntimeError("OOO product cabinet unverified")
    selected=[r["id"] for r in cabinets if r.get("selected")]
    if len(selected)>1:raise RuntimeError("Ambiguous original selection")
    try:
        tool("lk_wb_cabinets",{"action":"select","id":10014167})
        current=tool("lk_wb_cabinets",{"action":"list"})
        if [r["id"] for r in current if r.get("selected")]!=[10014167]:raise RuntimeError("OOO selection failed")
        args={"date_from":str(START),"date_to":str(END),"start_row":0,"end_row":300}
        value=tool("lk_wb_products",args)
        value=complete_products(tool,args,value)
        save("ooo_api_products",value,args)
    finally:
        tool("lk_wb_cabinets",{"action":"select","id":selected[0]} if selected else {"action":"reset"})
    return {"campaign_ids":sorted(ids),"read_only":True}
def mpstats():
    result=discover(os.environ["MPSTATS_API_TOKEN"],read_checks=True,extra_reader=extra)
    snapshot("ooo_api_collection_receipt",CABINET,{"status":result.get("status"),"extra_reads":result.get("extra_reads"),"detail":result.get("detail"),"retry_after":result.get("retry_after")})
attempt("ooo_api_collection_receipt",mpstats)
