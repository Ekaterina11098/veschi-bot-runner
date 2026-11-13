"""One-off owner-authorized recovery of the exact FBS consignments from 12 Nov 2026."""
import copy,datetime as dt,json,os
import fbs_document_chain as m
from fbs_wb_cabinets import ScopedCache

DAY="2026-11-12"
ROOT="fbs_recovery:20261112:"
TYPES=m.TYPES
WB_SCOPE={
 "china":["WB-GI-309089025","WB-GI-309089279","WB-GI-309138172","WB-GI-309228081","WB-GI-309253088","WB-GI-309257553"],
 "ip":["WB-GI-309254740"],
 "ooo":["WB-GI-309254456"],
}
OZON_ACT=126175078
tokens={k:os.environ["WB_TOKEN_"+v] for k,v in {"china":"3","ip":"2","ooo":"1"}.items()}
t=m.Transport();db=m.Cache(t)
census=db.get(ROOT+"census:v1")
if not census or census.get("status")!="inspected":
    raise m.Stop("Read-only census not complete")
if set(census["wb"])!=set(WB_SCOPE):
    raise m.Stop("WB census cabinet scope changed")
for cabinet,ids in WB_SCOPE.items():
    observed={row["supply_id"]:row for row in census["wb"][cabinet]}
    if set(observed)!=set(ids):
        raise m.Stop("WB census supply IDs differ for "+cabinet)
    for sid in ids:
        row=observed[sid]
        if any(row["documents"].get(kind) for kind in TYPES) or row["manual_orders"]:
            raise m.Stop("Census detected existing WB document: "+sid)
if len(census["ozon"])!=1 or census["ozon"][0]["act_id"]!=OZON_ACT or any(census["ozon"][0]["documents"].get(k) for k in TYPES):
    raise m.Stop("Ozon census act or document scope changed")
report={"at":m.now(),"day":DAY,"status":"running","completed":[],"blocked":[]}

def save():
    db.put(ROOT+"execution:v1",report)
def stop(cabinet,identity,error):
    report["blocked"].append({"cabinet":cabinet,"id":identity,"reason":str(error) if isinstance(error,m.Stop) else type(error).__name__})
    save()
def readback(worker,state,cabinet):
    expected_qty=sum(p["quantity"] for p in state["positions"])
    for typ in TYPES:
        info=state["documents"][typ]
        doc=t.request(m.MS,"entity/"+typ+"/"+info["id"])
        expected_store=state.get("warehouse_routing",{}).get("return_store_id" if typ=="salesreturn" else "source_store_id")
        if not expected_store:
            expected_store=worker.c["templates"][typ]["store"]["meta"]["href"].rsplit("/",1)[-1]
        if m.href(doc.get("store",{})).rsplit("/",1)[-1]!=expected_store:
            raise m.Stop("Warehouse mismatch after document creation")
        if doc.get("applicable") is not True or doc.get("sum")!=0:
            raise m.Stop("Document not posted or nonzero")
        positions=worker.ms_rows("entity/"+typ+"/"+info["id"]+"/positions")
        if sum(p["quantity"] for p in positions)!=expected_qty or any(p["price"]!=0 for p in positions):
            raise m.Stop("Position/price readback mismatch")
    return {"quantity":expected_qty,"documents":{k:v["name"] for k,v in state["documents"].items()}}

for cabinet,ids in WB_SCOPE.items():
    os.environ["WB_TOKEN_3"]=tokens[cabinet]
    m.CONFIG="fbs_document_chain:"+cabinet+":config:v1"
    m.STATE="fbs_document_chain:"+cabinet+":state:v1"
    m.PREFIX="fbs_document_chain:"+cabinet+":supply:v1:"
    cache=ScopedCache(t,cabinet)
    c=copy.deepcopy(cache.get(m.CONFIG))
    if not c or c.get("status")!="active" or not c.get("writes_enabled") or not c.get("scope_confirmed"):
        raise m.Stop("Inactive WB cabinet: "+cabinet)
    c["execution_policy"]={**c.get("execution_policy",{}),"forbid_negative_stock":True}
    w=m.Worker(t,cache,c)
    supplies={s["id"]:s for s in w.supplies() if s["id"] in ids}
    for sid in ids:
        try:
            if sid not in supplies or not supplies[sid].get("done"):
                raise m.Stop("WB supply not present or not closed")
            supply=supplies[sid]
            if m.stamp(supply["closedAt"]).astimezone(dt.timezone(dt.timedelta(hours=3))).date().isoformat()!=DAY:
                raise m.Stop("WB closed date changed")
            key=m.PREFIX+sid
            prior=cache.get(key)
            if prior:
                if sid!="WB-GI-309138172" or cabinet!="china" or prior.get("status")!="complete":
                    raise m.Stop("Existing ledger entry requires reconciliation")
                if set(prior.get("documents",{}))!=set(TYPES):
                    raise m.Stop("Expected old three-document journal missing")
                if prior.get("inflight"):
                    raise m.Stop("Previous uncertain document write")
                # An already-complete journal may be stale after manual deletion.
                if sum(x["quantity"] for x in prior["positions"])!=2:
                    raise m.Stop("Pilot original positions differ")
            existing={}
            for typ in TYPES:
                ext=c.get("document_prefix","fbs-china")+":"+sid+":"+typ
                existing[typ]=w.ms_rows("entity/"+typ,{"filter":"externalCode="+ext})
            manual=w.ms_rows("entity/customerorder",{"filter":"name="+sid})
            if any(existing.values()) or manual:
                raise m.Stop("Live existing documents found; do not recreate")
            state=copy.deepcopy(prior) if prior else {"supply":supply,"discovered_at":m.now()}
            state["supply"]=supply
            for key_drop in ("documents","inflight","error","last_error_at","completed_at","order_annotation"):
                state.pop(key_drop,None)
            state["status"]="discovered"
            # Ensure the archived pick list is still valid before any document is created.
            if prior:
                w.validate_source(state)
            w._execution_permit={"kind":"manual","supply_ids":{sid}}
            w.process(state)
            if state.get("status")!="complete":
                raise m.Stop("WB chain not complete")
            result=readback(w,state,cabinet)
            report["completed"].append({"cabinet":cabinet,"id":sid,**result})
            save()
        except Exception as error:
            stop(cabinet,sid,error)

# Ozon is an entirely independent cabinet and only its exact original act is recovered.
try:
    from fbs_ozon_chain import acts,snapshot,OzonWorker,virtual_supply,CONFIG,PREFIX
    m.CONFIG=CONFIG;m.PREFIX=PREFIX
    config=copy.deepcopy(db.get(CONFIG))
    if not config or config.get("status")!="active" or not config.get("writes_enabled") or not config.get("scope_confirmed"):
        raise m.Stop("Ozon configuration inactive")
    config["execution_policy"]={**config.get("execution_policy",{}),"forbid_negative_stock":True}
    matches=[a for a in acts() if a["id"]==OZON_ACT and a.get("departure_date")==DAY]
    if len(matches)!=1:raise m.Stop("Original Ozon act missing or date changed")
    act=matches[0]
    scope=snapshot(act)
    if not scope["ready"] or not scope["included"]:
        raise m.Stop("Ozon act has not reached delivery handover")
    key=PREFIX+"OZON-ACT-"+str(OZON_ACT)
    if db.get(key):
        raise m.Stop("Existing Ozon ledger requires reconciliation")
    w=OzonWorker(t,db,config,act,scope)
    positions,posting_ids=w.positions(virtual_supply(act,scope))
    for typ in TYPES:
        ext=config["document_prefix"]+":OZON-ACT-"+str(OZON_ACT)+":"+typ
        if w.ms_rows("entity/"+typ,{"filter":"externalCode="+ext}):
            raise m.Stop("Existing Ozon document detected")
    for name in [w.order_name,w.order_name+" "+str(OZON_ACT)]:
        if any(set(posting_ids)&set((d.get("description") or "").replace(" ","").split(",")) for d in w.ms_rows("entity/customerorder",{"filter":"name="+name})):
            raise m.Stop("Manual Ozon order already includes act")
    state={"act":act,"supply":virtual_supply(act,scope),"picking_scope":scope,
           "positions":positions,"order_ids":posting_ids,"status":"prepared"}
    w._execution_permit={"kind":"manual","supply_ids":{state["supply"]["id"]}}
    demand=copy.deepcopy(config["templates"]["demand"]);demand["positions"]=positions
    w.require_available_stock(demand,state)
    w.process(state)
    if state.get("status")!="complete":raise m.Stop("Ozon chain not complete")
    report["completed"].append({"cabinet":"ozon","id":OZON_ACT,**readback(w,state,"ozon")})
    save()
except Exception as error:
    stop("ozon",str(OZON_ACT),error)

report["status"]="complete" if not report["blocked"] else "requires_attention"
report["finished_at"]=m.now()
save()
print(json.dumps({"status":report["status"],"completed":report["completed"],"blocked":report["blocked"]},ensure_ascii=False))
if report["blocked"]:raise SystemExit(1)
