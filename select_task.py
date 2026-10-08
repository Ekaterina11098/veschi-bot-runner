"""Select work without calling marketplace APIs or logging operational data."""
import json, os, re, time, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

SCHEDULES = {"45 4 * * *": "reviews", "27 7,11,15,19 * * *": "advertising",
             "30 13 * * *": "stock", "17 4 * * *": "daily", "0 7 * * *": "finance",
             "3-59/5 * * * *": "queue", "3-58/5 * * * *": "queue"}
TASKS = {"daily", "daily_context", "reviews", "advertising", "stock", "analytics", "finance", "queue", "probe", "agent"}
GROUPS = {"daily_context": "advertising-and-finance", "stock": "stock-and-commands", "stock_retry": "stock-and-commands",
          "telegram_queue": "telegram-commands", "review_queue": "review-replies",
          "advertising": "advertising-and-finance", "finance": "advertising-and-finance",
          "advertising_report_retry": "advertising-and-finance", "finance_retry": "advertising-and-finance", "agent":"advertising-agent-conversations",
          "business_agent":"business-agent-conversations","advertising_research":"advertising-and-finance","mpstats_recovery":"mpstats-data","analytics_recovery":"advertising-and-finance"}

def recovery_work(now=None):
    now=now or datetime.now(timezone.utc)
    try:
        rows=database('telegram_api_cache',{'cache_key':'like.analytics:recovery:%',
            'payload->>status':'eq.pending','expires_at':'gt.'+now.isoformat(),
            'select':'payload','order':'updated_at.asc','limit':'20'}) or []
        return [{'task':'analytics_recovery','group':GROUPS['analytics_recovery']}] if any(
            r['payload'].get('next_retry_at') and now>=datetime.fromisoformat(r['payload']['next_retry_at']) for r in rows) else []
    except Exception:return []


def mpstats_work(now=None):
    now=now or datetime.now(timezone.utc)
    try:
        rows=database('telegram_api_cache',{'cache_key':'eq.mpstats:gap_requests:v1','select':'payload','limit':'1'})
        state=rows[0]['payload'] if rows else {}
        pause=database('telegram_api_cache',{'cache_key':'eq.mpstats:cooldown','expires_at':'gt.'+now.isoformat(),'select':'payload','limit':'1'})
        if pause:return []
        if state.get('next_retry_at') and now<datetime.fromisoformat(state['next_retry_at']):return []
        local=now.astimezone(ZoneInfo('Europe/Moscow'))
        due=bool(state.get('requests') or state.get('normalization_pending')) or (local.hour>=7 and state.get('planned_day')!=str(local.date()))
        if not due:
            stock=database('telegram_api_cache',{'cache_key':'like.mpstats:stock-request:%',
                'expires_at':'gt.'+now.isoformat(),'select':'payload,updated_at','limit':'3'}) or []
            due=any(row.get('payload',{}).get('mpstats_requests') and
                    row.get('updated_at','')>state.get('last_stock_ingested_at','') for row in stock)
        if not due:
            requests=database('telegram_api_cache',{'cache_key':'like.analytics:recovery:%',
                'expires_at':'gt.'+now.isoformat(),'select':'payload,updated_at','order':'updated_at.desc','limit':'1'}) or []
            due=bool(requests and requests[0]['payload'].get('mpstats_requests') and
                requests[0]['updated_at']>state.get('last_recovery_ingested_at',''))
        return [{'task':'mpstats_recovery','group':GROUPS['mpstats_recovery']}] if due else []
    except Exception:
        return []

def research_work():
    try:
        rows=database('telegram_api_cache',{'cache_key':'eq.advertising:research_request','select':'payload','limit':'1',
            'expires_at':'gt.'+datetime.now(timezone.utc).isoformat()})
        return [{'task':'advertising_research','group':GROUPS['advertising_research']}] if rows and rows[0].get('payload',{}).get('pending') else []
    except Exception:
        return []

def business_due():
    now=datetime.now(timezone.utc).isoformat()
    try:
        return bool(database("business_agent_jobs",{"select":"id","limit":"1","attempts":"lt.4",
            "or":f"(and(status.eq.pending,retry_at.lte.{now}),and(status.eq.running,lease_until.lte.{now}))"}))
    except Exception:
        return True

def agent_due():
    now=datetime.now(timezone.utc).isoformat()
    checks=(
        ("advertising_agent_jobs",{"attempts":"lt.4","or":f"(and(status.in.(pending,ready),retry_at.lte.{now}),and(status.eq.running,lease_until.lte.{now}))"}),
        ("advertising_agent_watches",{"status":"eq.active","next_check_at":"lte."+now}),
        ("advertising_agent_actions",{"or":"(status.eq.submitted,and(status.eq.executed,receipt->>notification_pending.eq.true))"}),
    )
    try:
        return any(database(table,{"select":"id","limit":"1",**params}) for table,params in checks)
    except Exception:
        return True

def evening_target_date(now=None):
    local=(now or datetime.now(timezone.utc)).astimezone(ZoneInfo("Europe/Moscow"))
    if local.hour<9:
        return (local.date()-timedelta(days=1)).isoformat()
    # Give the normal 22:30 collection time to finish; fallback starts at 23:00.
    if (local.hour,local.minute)>=(23,0):
        return local.date().isoformat()
    return None

def evening_recovery_work(now=None):
    target=evening_target_date(now)
    if not target:
        return []
    try:
        rows=database("telegram_api_cache",{"select":"payload","limit":"1",
                      "cache_key":"eq.advertising:last_evening_report"})
        state=rows[0].get("payload") if rows else {}
        if state and state.get("date")==target and state.get("complete"):
            return []
    except Exception:
        # The serialized delivery worker rechecks its marker before sending.
        pass
    return [{"task":"advertising_report_retry","group":GROUPS["advertising_report_retry"]}]

def database(table, params):
    key=os.environ["SUPABASE_SECRET_KEY"].strip()
    headers={"apikey":key}
    if not key.startswith("sb_secret_"):
        headers["Authorization"]="Bearer "+key
    url=os.environ["SUPABASE_URL"].strip().rstrip("/")+"/rest/v1/"+table+"?"+urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=20) as r:
        return json.load(r)

def finance_retry_work(now=None):
    now = now or datetime.now(timezone.utc)
    try:
        daily = database("telegram_api_cache", {
            "cache_key":"in.(finance:daily:token_1:v1,finance:daily:token_2:v1,finance:daily:token_3:v1)",
            "select":"payload","limit":"3"}) or []
        daily = [item for item in daily if isinstance(item.get("payload"),dict)]
        for item in daily:
            state = item.get("payload") or {}
            if state.get("status") in {"pending", "running"} and state.get("next_retry_at"):
                retry_at = datetime.fromisoformat(state["next_retry_at"].replace("Z", "+00:00"))
                if now >= retry_at:
                    return [{"task":"finance_retry","group":GROUPS["finance_retry"]}]
        if daily:
            return []
        rows = database("analytics_snapshots", {
            "source": "eq.finance_ip_daily_summary", "cabinet": "eq.token_2",
            "select": "status,collected_at,detail", "order": "collected_at.desc", "limit": "20"})
        # Cache refreshes can append a partial summary while a WB cooldown is
        # pending. They do not cancel the last deferred collection. A completed
        # collection or a later processing error does stop automatic retries.
        if not rows or rows[0].get("status") in {"complete", "error"}:
            return []
        row = next((item for item in rows if item.get("status") == "deferred"), None)
        if row is None:
            return []
        observed = datetime.fromisoformat(row["collected_at"].replace("Z", "+00:00"))
        if observed.astimezone(ZoneInfo("Europe/Moscow")).date() != now.astimezone(ZoneInfo("Europe/Moscow")).date():
            return []
        match = re.search(r"Finance API 429; retry_after=(\d+)", row.get("detail") or "")
        delay = max(60, int(match[1])) if match else 900
        if now < observed + timedelta(seconds=delay + 60):
            return []
        return [{"task": "finance_retry", "group": GROUPS["finance_retry"]}]
    except Exception:
        # Missing cooldown state must not generate another marketplace request.
        return []

def queue_work():
    now=datetime.now(timezone.utc).isoformat()
    checks = (
        ("telegram_queue", "telegram_jobs", {"select":"id","limit":"1",
         "or":f"(and(status.eq.pending,retry_at.lte.{now}),and(status.eq.running,lease_until.lte.{now}))"}),
        ("review_queue", "review_replies", {"select":"feedback_id","limit":"1",
         "state":"eq.pending","retry_at":"lte."+str(int(time.time()))}),
        ("stock_retry", "telegram_api_cache", {"select":"payload","limit":"1",
         "cache_key":"eq.stock-retry","expires_at":"gt."+now}),
    )
    work = []
    for task, table, params in checks:
        try:
            rows = database(table, params)
            if task == "stock_retry":
                stock = rows[0].get("payload") if rows else None
                due = bool(stock and stock.get("pending") and
                           stock.get("due",float("inf")) <= time.time())
            else:
                due = bool(rows)
        except Exception:
            # Let this worker report its own failure without blocking siblings.
            print("Queue check unavailable: " + task)
            due = True
        if due:
            work.append({"task":task, "group":GROUPS[task]})
    if agent_due():
        work.append({"task":"agent","group":GROUPS["agent"]})
    if business_due():
        work.append({"task":"business_agent","group":GROUPS["business_agent"]})
    return work+evening_recovery_work()+finance_retry_work()+research_work()+mpstats_work()+recovery_work()

def queue_due():
    return bool(queue_work())

def main():
    if os.getenv("GITHUB_EVENT_NAME")=="workflow_dispatch":
        task=os.getenv("REQUESTED_TASK") or "probe"
    elif os.getenv("GITHUB_EVENT_NAME")=="push":
        task="daily"
    else:
        task=SCHEDULES.get(os.getenv("EVENT_SCHEDULE"))
    if task not in TASKS:
        raise ValueError("Unknown task")
    work = ([{"task":name,"group":GROUPS.get(name,name)} for name in ("analytics","daily_context","finance")]
            if task == "daily" else queue_work() if task == "queue" else [{"task":task,"group":GROUPS.get(task,task)}])
    run=bool(work)
    with open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8") as f:
        f.write(f"task={task}\nrun={str(run).lower()}\n")
        f.write("group="+GROUPS.get(task,task)+"\n")
        f.write("matrix="+json.dumps({"include":work},separators=(",",":"))+"\n")
    print("Work available." if run else "Queue idle; no marketplace calls.")

if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print("Task selection failed: "+type(exc).__name__)
        raise SystemExit(1)



