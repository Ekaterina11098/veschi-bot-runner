"""Explicit one-supply live verification; does not enable the scheduler."""
import copy,json,sys
from fbs_document_chain import Transport,Cache,Worker,Stop,MS,WB,CONFIG,PREFIX,TYPES,now,meta,href
SID="WB-GI-296250890"
PROOF="fbs_document_chain:china:pilot:v1"
def main():
    t=Transport(); db=Cache(t); config=db.get(CONFIG)
    if not config or config.get("cabinet")!="token_3" or config.get("scope_confirmed") is not True:
        raise Stop("Confirmed China configuration missing")
    permission=config.get("pilot",{})
    if permission.get("supply_id")!=SID or permission.get("authorized") is not True:
        raise Stop("Exact pilot authorization missing")
    worker=Worker(t,db,config)
    supply=t.request(WB,"api/v3/supplies/"+SID)
    if supply.get("id")!=SID or supply.get("done") is not True or not supply.get("closedAt"):
        raise Stop("Exact pilot supply is not in delivery")
    try:
        positions,ids=worker.positions(supply)
    except Stop as exc:
        if "595-Noelbag-zblack" in str(exc):
            candidates=worker.ms_rows("entity/product",{"search":"595"})
            db.put(PROOF,{"supply_id":SID,"status":"mapping_blocked","error":str(exc),"candidates":[{k:p.get(k) for k in ("id","name","article","archived","variantsCount","trackingType","meta")} for p in candidates]})
        raise
    key=PREFIX+SID
    state=db.get(key) or {"supply":supply,"positions":positions,"order_ids":ids,"status":"pilot_prepared","historical_exception":True}
    if "positions" in state and (state["positions"]!=positions or state["order_ids"]!=ids):
        raise Stop("Prepared composition differs from current supply")
    proof={"supply_id":SID,"at":now(),"orders":len(ids),"positions":len(positions),
           "quantity":sum(p["quantity"] for p in positions),"status":"preflight","scheduler_enabled":False}
    db.put(PROOF,proof)
    # Fail before any write when manually entered documents already exist.
    manual=worker.ms_rows("entity/customerorder",{"filter":"name="+SID})
    managed=worker.ms_rows("entity/customerorder",{"filter":"externalCode=fbs-china:"+SID+":customerorder"})
    if manual and (len(manual)!=1 or not managed or manual[0]["id"]!=managed[0]["id"]):
        proof.update(status="existing_manual_order",documents=[{"id":d["id"],"name":d["name"]} for d in manual])
        db.put(PROOF,proof)
        raise Stop("Existing manual order: reconcile instead of creating duplicate")
    try:
        worker.process(state)
        # Verify a second pass is read-only and does not create duplicates.
        original=t.request
        def no_document_writes(base,path,method="GET",body=None,params=None):
            if base==MS and method!="GET":raise Stop("Idempotency verification attempted document write")
            return original(base,path,method,body,params)
        t.request=no_document_writes
        worker.process(state)
        proof.update(status="verified",documents=state["documents"],posted=True,zero_prices=True,
                     idempotent_rerun=True,completed_at=now())
        db.put(PROOF,proof)
        latest=db.get(CONFIG)
        latest["pilot"]["authorized"]=False
        latest["pilot"]["completed_at"]=now()
        latest["verification"]["live_chain_verified"]=True
        latest["verification"]["pilot_supply"]=SID
        latest["status"]="live_verified_scheduler_paused"
        db.put(CONFIG,latest)
        print(json.dumps({"status":"verified","orders":len(ids),"positions":len(positions),"documents":3}))
    except Exception as exc:
        message=str(exc) if isinstance(exc,Stop) else type(exc).__name__
        state["error"]=message;state["last_error_at"]=now();db.put(key,state)
        proof.update(status="failed",error=message,documents=state.get("documents",{}));db.put(PROOF,proof)
        raise
if __name__=="__main__":
    try:main()
    except Exception as exc:
        print(json.dumps({"status":"failed","error":str(exc) if isinstance(exc,Stop) else type(exc).__name__}))
        sys.exit(1)
