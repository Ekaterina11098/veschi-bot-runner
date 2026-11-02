"""Focused read-only OOO periods after configuration change; never WB traffic."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path("private-source").resolve()))
from analytics.collect import database,snapshot
from analytics.mpstats_probe import discover,unpack_tool,sanitize
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
CABINET="token_1"
end=datetime.now(ZoneInfo("Europe/Moscow")).date()-timedelta(days=1)
def latest(source):
    rows=database("GET","analytics_snapshots",params={"source":"eq."+source,"cabinet":"eq."+CABINET,"status":"eq.complete","select":"payload","order":"id.desc","limit":1}) or []
    if not rows:raise RuntimeError("Required private source unavailable")
    return rows[0]["payload"]
config=latest("ooo_owner_configuration")["adverts"]
catalog=latest("ooo_api_campaign_catalog")["data"]["data"]
mapping={int(r["wb_id"]):int(r["id"]) for r in catalog}
def extra(call,checks,seen):
    saved=[]
    for cfg in config:
        cid=int(cfg["id"])
        if cid not in mapping:raise RuntimeError("Campaign mapping unavailable")
        changed=datetime.fromisoformat(cfg["timestamps"]["updated"]).astimezone(ZoneInfo("Europe/Moscow")).date()
        windows={("last7",end-timedelta(days=6),end)}
        if cfg["status"]==9 and changed<end:windows.add(("after_change",changed+timedelta(days=1),end))
        for label,start,finish in sorted(windows):
            args={"campaign_id":mapping[cid],"d1":str(start),"d2":str(finish),"zone":"all","report":"products"}
            value=sanitize(unpack_tool(call("tools/call",{"name":"wbbidder_campaign_stats","arguments":args})))
            rows=value.get("data")
            if not isinstance(rows,list):raise RuntimeError("Product report schema invalid")
            body={"wb_campaign_id":cid,"window":label,"arguments":args,"data":value,"config_updated":cfg["timestamps"]["updated"]}
            snapshot("ooo_api_focused_products",CABINET,body,period_from=start,period_to=finish)
            saved.append({"campaign_id":cid,"window":label,"rows":len(rows)})
    return saved
try:
    result=discover(os.environ["MPSTATS_API_TOKEN"],read_checks=True,extra_reader=extra)
    snapshot("ooo_api_focused_receipt",CABINET,{"status":result.get("status"),"extra_reads":result.get("extra_reads"),"retry_after":result.get("retry_after")})
    print("Focused OOO evidence stored privately; no WB requests",flush=True)
except Exception as exc:
    snapshot("ooo_api_focused_receipt",CABINET,None,"error",str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__)
    raise RuntimeError("Focused source collection failed; see private receipt") from None
