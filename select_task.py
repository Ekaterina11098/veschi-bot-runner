"""Select work without calling marketplace APIs or logging operational data."""
import json, os, re, time, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

SCHEDULES = {"45 4 * * *": "reviews", "27 7,11,15,19 * * *": "advertising",
             "30 13 * * *": "stock", "17 4 * * *": "daily", "0 7 * * *": "mpstats_recovery",
             "3-59/5 * * * *": "queue", "3-58/5 * * * *": "queue"}
TASKS = {"mpstats_recovery", "daily", "daily_context", "reviews", "advertising", "stock", "analytics", "finance", "queue", "probe", "agent"}
GROUPS = {"daily_context": "advertising-and-finance", "stock": "stock-and-commands", "stock_retry": "stock-and-commands",
          "telegram_queue": "telegram-commands", "review_queue": "review-replies",
          "advertising": "advertising-and-finance", "finance": "mpstats-data",
          "advertising_report_retry": "advertising-and-finance", "finance_retry": "mpstats-data", "agent":"advertising-agent-conversations",
          "business_agent":"business-agent-conversations","advertising_research":"advertising-and-finance","mpstats_recovery":"mpstats-data","analytics_recovery":"advertising-and-finance","budget_retry":"advertising-and-finance"}

def review_inbox_work(now=None):
    try:
        now=now or datetime.now(timezone.utc)
        local=now.astimezone(ZoneInfo('Europe/Moscow'))
        if (local.hour,local.minute)<(7,45):return []
        rows=database('telegram_api_cache',{'cache_key':'like.reviews:refresh-state:%','select':'payload','limit':'3'}) or []
        states=[r.get('payload') or {} for r in rows]
        due=len(states)<3
        for state in states:
            retry=state.get('next_retry_at')
            if retry:
                due=due or now>=datetime.fromisoformat(retry)
            elif not state.get('observed_at') or datetime.fromisoformat(state['observed_at']).astimezone(ZoneInfo('Europe/Moscow')).date()!=local.date():due=True
        return [{'task':'review_inbox_retry','group':'review-replies'}] if due else []
    except Exception:return []

def budget_work(now=None):
    now=now or datetime.now(timezone.utc)
    try:
        rows=database('analytics_snapshots',{'source':'eq.advertising_campaign_budgets',
            'cabinet':'eq.token_2','select':'payload','order':'collected_at.desc','limit':'1'}) or []
        payload=rows[0].get('payload') if rows else None
        if not isinstance(payload,dict) or not payload.get('campaign_ids'):
            return []
        deadline=payload.get('next_retry_at')
        if deadline and now<datetime.fromisoformat(deadline.replace('Z','+00:00')):
            return []
        return [{'task':'budget_retry','group':GROUPS['budget_retry']}]
    except Exception:
        return []


def recovery_work(now=None):
    now=now or datetime.now(timezone.utc)
    try:
        rows=database('telegram_api_cache',{'cache_key':'like.analytics:recovery:%',
            'payload->>status':'eq.pending','expires_at':'gt.'+now.isoformat(),
            'select':'next_retry_at:payload->next_retry_at','order':'updated_at.asc','limit':'20'}) or []
        return [{'task':'analytics_recovery','group':GROUPS['analytics_recovery']}] if any(
            (r.get('next_retry_at') or (r.get('payload') or {}).get('next_retry_at')) and now>=datetime.fromisoformat(r.get('next_retry_at') or r['payload']['next_retry_at']) for r in rows) else []
    except Exception:return []


def mpstats_work(now=None):
    now=now or datetime.now(timezone.utc)
    try:
        rows=database('telegram_api_cache',{'cache_key':'eq.mpstats:gap_requests:v1','select':'requests:payload->requests->0,normalization_pending:payload->normalization_pending,next_retry_at:payload->next_retry_at,planned_day:payload->planned_day,last_stock_ingested_at:payload->last_stock_ingested_at,last_recovery_ingested_at:payload->last_recovery_ingested_at','limit':'1'})
        state=(rows[0].get('payload') or rows[0]) if rows else {}
        pause=database('telegram_api_cache',{'cache_key':'eq.mpstats:cooldown','expires_at':'gt.'+now.isoformat(),'select':'payload','limit':'1'})
        if pause:return []
        if state.get('next_retry_at') and now<datetime.fromisoformat(state['next_retry_at']):return []
        local=now.astimezone(ZoneInfo('Europe/Moscow'))
        due=bool(state.get('requests') or state.get('normalization_pending')) or (local.hour>=7 and state.get('planned_day')!=str(local.date()))
        if not due:
            stock=database('telegram_api_cache',{'cache_key':'like.mpstats:stock-request:%',
                'expires_at':'gt.'+now.isoformat(),'select':'mpstats_requests:payload->mpstats_requests->0,updated_at','limit':'3'}) or []
            due=any((row.get('mpstats_requests') or (row.get('payload') or {}).get('mpstats_requests')) and
                    row.get('updated_at','')>state.get('last_stock_ingested_at','') for row in stock)
        if not due:
            requests=database('telegram_api_cache',{'cache_key':'like.analytics:recovery:%',
                'expires_at':'gt.'+now.isoformat(),'select':'mpstats_requests:payload->mpstats_requests->0,updated_at','order':'updated_at.desc','limit':'1'}) or []
            due=bool(requests and (requests[0].get('mpstats_requests') or (requests[0].get('payload') or {}).get('mpstats_requests')) and
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
    """WB finance confirmation retries are disabled under MPStats primary."""
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
    return work+review_inbox_work()+evening_recovery_work()+finance_retry_work()+research_work()+mpstats_work()+recovery_work()+budget_work()

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
    work = ([{"task":name,"group":GROUPS.get(name,name)} for name in ("analytics","daily_context","mpstats_recovery")]
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
