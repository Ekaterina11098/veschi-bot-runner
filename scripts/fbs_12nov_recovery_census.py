"""Read-only 12 Nov FBS recovery census. Never mutate marketplace or MoySklad."""
import datetime as dt, json, os
import fbs_document_chain as m
from fbs_wb_cabinets import ScopedCache
from fbs_ozon_chain import acts, snapshot, CONFIG as OZ_CONFIG, PREFIX as OZ_PREFIX

DAY="2026-11-12"
ROOT="fbs_recovery:20261112:"
class ReadOnly(m.Transport):
    def request(self,base,path,method="GET",body=None,params=None):
        if base==m.MS and method!="GET":raise m.Stop("MoySklad write blocked in census")
        return super().request(base,path,method,body,params)

t=ReadOnly()
db=m.Cache(t)
result={"at":m.now(),"day":DAY,"status":"reading","wb":{},"ozon":[],"errors":[]}
tokens={k:os.environ["WB_TOKEN_"+v] for k,v in {"china":"3","ip":"2","ooo":"1"}.items()}
for cabinet in ("china","ip","ooo"):
    try:
        os.environ["WB_TOKEN_3"]=tokens[cabinet]
        m.CONFIG="fbs_document_chain:"+cabinet+":config:v1"
        m.STATE="fbs_document_chain:"+cabinet+":state:v1"
        m.PREFIX="fbs_document_chain:"+cabinet+":supply:v1:"
        cache=ScopedCache(t,cabinet)
        config=cache.get(m.CONFIG)
        worker=m.Worker(t,cache,config)
        rows=[]
        for supply in worker.supplies():
            if not supply.get("closedAt") or not supply.get("done"):continue
            if m.stamp(supply["closedAt"]).astimezone(dt.timezone(dt.timedelta(hours=3))).date().isoformat()!=DAY:continue
            sid=supply["id"]
            state=cache.get(m.PREFIX+sid)
            found={}
            for kind in m.TYPES:
                ext=config.get("document_prefix","fbs-"+cabinet)+":"+sid+":"+kind
                docs=worker.ms_rows("entity/"+kind,{"filter":"externalCode="+ext})
                found[kind]=[{"id":d["id"],"name":d["name"],"posted":d.get("applicable"),"store":m.href(d.get("store",{}))} for d in docs]
            manual=worker.ms_rows("entity/customerorder",{"filter":"name="+sid})
            rows.append({"supply_id":sid,"name":supply.get("name"),"closed_at":supply["closedAt"],"state":state.get("status") if state else None,"inflight":state.get("inflight") if state else None,"documents":found,"manual_orders":[{"id":d["id"],"name":d["name"]} for d in manual]})
        result["wb"][cabinet]=rows
    except Exception as e:
        result["errors"].append({"cabinet":cabinet,"error":str(e) if isinstance(e,m.Stop) else type(e).__name__})
    db.put(ROOT+"census:v1",result)
try:
    os.environ["WB_TOKEN_3"]=tokens["china"]
    m.CONFIG=OZ_CONFIG
    m.PREFIX=OZ_PREFIX
    config=db.get(OZ_CONFIG)
    worker=m.Worker(t,db,config)
    for act in acts():
        if act.get("departure_date")!=DAY:continue
        sid="OZON-ACT-"+str(act["id"])
        state=db.get(OZ_PREFIX+sid)
        found={}
        for typ in m.TYPES:
            ext=config["document_prefix"]+":"+sid+":"+typ
            docs=worker.ms_rows("entity/"+typ,{"filter":"externalCode="+ext})
            found[typ]=[{"id":d["id"],"name":d["name"],"posted":d.get("applicable")} for d in docs]
        result["ozon"].append({"act_id":act["id"],"state":state.get("status") if state else None,"documents":found})
except Exception as e:
    result["errors"].append({"cabinet":"ozon","error":str(e) if isinstance(e,m.Stop) else type(e).__name__})
result["status"]="inspected" if not result["errors"] else "partial"
db.put(ROOT+"census:v1",result)
print(json.dumps({"status":result["status"],"wb":{k:len(v) for k,v in result["wb"].items()},"ozon":len(result["ozon"]),"errors":result["errors"]},ensure_ascii=False))
