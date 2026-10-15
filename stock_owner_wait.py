"""Wait only for the recorded WB RetryAfter; no source calls or stock writes."""
import json,time,sys
from stock_deploy_support import *
def main():
    db=runtime_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT snapshot FROM stock_execution.stock_runs WHERE id=%s",('owner-controlled-first-three-20261015',))
            row=cur.fetchone();assert row
            cache=json.loads(row[0]).get('cache',{})
        db.commit()
        untils=[float(v['until']) for key,v in cache.items() if key.startswith('wb-pause:') and isinstance(v,dict) and 'until' in v]
        assert untils,'Recorded RetryAfter not available'
        until=max(untils)+2
        wait=max(0,until-time.time());assert wait<=5400
        print(json.dumps({'waiting_for_recorded_retry_after':True,'not_before_utc_epoch':until,'wait_seconds':round(wait),'wb_calls':0}),flush=True)
        db.close()
        while time.time()<until:time.sleep(min(30,max(0,until-time.time())))
        print('Recorded RetryAfter elapsed; fresh preflight may resume.',flush=True)
    except BaseException as exc:
        seal('wait-error',dict(error=error(exc)));raise SystemExit(type(exc).__name__)
if __name__=='__main__':main()
