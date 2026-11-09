"""Daily Ozon document execution, independent of WB, fail-closed and once per Moscow day."""
import datetime as dt, json, os
import fbs_ozon_chain as oz
import fbs_document_chain as m

def main():
    now=dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=3)))
    if now.hour != 19 or os.environ.get("FBS_EXECUTION_KIND") != "daily":
        raise m.Stop("Ozon daily run is allowed only at 19:00 Moscow")
    t=m.Transport()
    db=m.Cache(t)
    config=db.get(oz.CONFIG)
    if not config or config.get("cabinet")!="ozon" or config.get("status")!="active" or config.get("writes_enabled") is not True or config.get("scope_confirmed") is not True:
        raise m.Stop("Ozon daily configuration is inactive or unconfirmed")
    key="fbs_document_chain:ozon:daily_execution:v1:"+now.date().isoformat()
    receipt={"at":m.now(),"cabinet":"ozon","local_date":now.date().isoformat(),"github_run_id":os.environ.get("GITHUB_RUN_ID")}
    if not db.claim(key,receipt):
        print(json.dumps({"status":"already_claimed","writes":0,"day":now.date().isoformat()}))
        return
    class GuardedOzonWorker(oz.OzonWorker):
        def __init__(self, transport, cache, c, act, scope):
            c=dict(c)
            c["execution_policy"]={**c.get("execution_policy",{}),"forbid_negative_stock":True}
            super().__init__(transport,cache,c,act,scope)
        def require_execution_permission(self,supply_id):
            if supply_id != "OZON-ACT-"+str(self.act["id"]):
                raise m.Stop("Ozon execution outside selected act")
            if os.environ.get("FBS_EXECUTION_KIND")!="daily":
                raise m.Stop("Non-daily execution prohibited")
    oz.OzonWorker=GuardedOzonWorker
    try:
        oz.main("run")
    except Exception as error:
        db.put("fbs_document_chain:ozon:daily_result:v1",{"at":m.now(),"day":now.date().isoformat(),"status":"failed","error":str(error) if isinstance(error,m.Stop) else type(error).__name__})
        raise
    result=db.get("fbs_document_chain:ozon:last_run:v1")
    db.put("fbs_document_chain:ozon:daily_result:v1",{"at":m.now(),"day":now.date().isoformat(),"status":"complete" if not result.get("errors") else "requires_attention","completed":result.get("completed"),"errors":result.get("errors",[])})
    if result.get("errors"):
        raise m.Stop("Ozon daily processing errors detected")

if __name__=="__main__":
    try:main()
    except Exception as e:
        print(json.dumps({"status":"failed","error":str(e) if isinstance(e,m.Stop) else type(e).__name__}))
        raise SystemExit(1)
