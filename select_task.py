"""Select work without calling marketplace APIs or logging operational data."""
import json, os, time, urllib.request, urllib.parse
from datetime import datetime, timezone

SCHEDULES = {"45 4 * * *": "reviews", "27 7,11,15,19 * * *": "advertising",
             "30 13 * * *": "stock", "17 4 * * *": "analytics", "0 7 * * *": "finance",
             "3-59/5 * * * *": "queue", "3-58/5 * * * *": "queue"}
TASKS = {"reviews", "advertising", "stock", "analytics", "finance", "queue", "probe"}
GROUPS = {"stock": "stock-and-commands", "stock_retry": "stock-and-commands",
          "telegram_queue": "telegram-commands", "review_queue": "review-replies",
          "advertising": "advertising-and-finance", "finance": "advertising-and-finance"}

def database(table, params):
    key=os.environ["SUPABASE_SECRET_KEY"].strip()
    headers={"apikey":key}
    if not key.startswith("sb_secret_"):
        headers["Authorization"]="Bearer "+key
    url=os.environ["SUPABASE_URL"].strip().rstrip("/")+"/rest/v1/"+table+"?"+urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=20) as r:
        return json.load(r)

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
    return work

def queue_due():
    return bool(queue_work())

def main():
    if os.getenv("GITHUB_EVENT_NAME")=="workflow_dispatch":
        task=os.getenv("REQUESTED_TASK") or "probe"
    else:
        task=SCHEDULES.get(os.getenv("EVENT_SCHEDULE"))
    if task not in TASKS:
        raise ValueError("Unknown task")
    work = queue_work() if task == "queue" else [{"task":task,"group":GROUPS.get(task,task)}]
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
