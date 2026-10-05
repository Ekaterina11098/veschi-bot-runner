"""Execute private source while keeping business output out of public logs."""
import asyncio, contextlib, os, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/"private-source"

def save_diagnostic(label, text):
    """Diagnostics stay in the existing protected backend, never public artifacts."""
    try:
        import requests
        from datetime import datetime, timedelta, timezone
        for name,value in os.environ.items():
            if name.startswith(("WB_","SUPABASE_","TELEGRAM_","ADVERTISING_","MOYSKLAD_")) and len(value)>=6:
                text=text.replace(value,"[redacted]")
        key=os.environ["SUPABASE_SECRET_KEY"]
        headers={"apikey":key,"Content-Type":"application/json","Prefer":"resolution=merge-duplicates"}
        if not key.startswith("sb_secret_"):
            headers["Authorization"]="Bearer "+key
        now=datetime.now(timezone.utc)
        response=requests.post(os.environ["SUPABASE_URL"].rstrip("/")+"/rest/v1/telegram_api_cache?on_conflict=cache_key",
            headers=headers,json={"cache_key":"runner:diagnostic:"+os.environ.get("GITHUB_RUN_ID","manual"),
            "payload":{"stage":label,"log":text[-20000:]},"updated_at":now.isoformat(),
            "expires_at":(now+timedelta(days=1)).isoformat()},timeout=(5,20))
        response.raise_for_status()
    except Exception:
        pass

def execute(label, args, optional=False):
    print(label, flush=True)
    child_env=dict(os.environ)
    if args==['auto_stock_runner.py']:
        child_env['AUTO_STOCK_MAX_SECONDS']='2400'
    if args[:2]==["-m","unittest"]:
        # Unit tests must never inherit live credentials or install live DB hooks.
        for name in list(child_env):
            if name.startswith(("WB_","SUPABASE_","TELEGRAM_","ADVERTISING_","MOYSKLAD_","AUTO_STOCK_")):
                child_env.pop(name)
    with tempfile.TemporaryFile() as log:
        result=subprocess.run([sys.executable]+args,cwd=SOURCE,env=child_env,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:
            log.seek(0)
            save_diagnostic(label,log.read().decode("utf-8",errors="replace"))
    if result.returncode and not optional:
        raise RuntimeError("Private task failed")
    if result.returncode:
        print("Optional source unavailable; missing data stays marked unavailable.",flush=True)

def hidden(function):
    with tempfile.TemporaryFile(mode="w+",encoding="utf-8") as log:
        with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
            return function()

def validate_stock():
    # Retain allocation, overselling, barcode, cache and timeout safeguards.
    # Advertising/media failures belong to their own task gates.
    for pattern in ("test_auto_stock.py", "test_stock_limits.py", "test_sales_cache.py"):
        execute("Validate stock logic: " + pattern,
                ["-m", "unittest", "discover", "-s", "tests", "-p", pattern])

def notify(text, advertising=False):
    import requests
    token=os.environ.get("ADVERTISING_TELEGRAM_BOT_TOKEN" if advertising else "TELEGRAM_BOT_TOKEN")
    chat=os.environ.get("TELEGRAM_ALLOWED_CHAT_ID")
    if advertising:
        from advertising_agent.notify import db
        chats=db("GET","advertising_telegram_chat",params={"is_active":"eq.true","select":"chat_id","limit":2}) or []
        if len(chats)!=1:
            raise RuntimeError("Advertising destination unavailable")
        chat=chats[0]["chat_id"]
    if not token or not chat:
        raise RuntimeError("Notification settings unavailable")
    r=requests.post("https://api.telegram.org/bot"+token+"/sendMessage",json={"chat_id":chat,"text":text},timeout=(5,20))
    if not r.ok or r.json().get("ok") is not True:
        raise RuntimeError("Notification delivery failed")

def reviews():
    from refresh_review_inbox import refresh
    feedbacks,questions=refresh()
    notify("📩 Проверка WB: отзывы без ответа — "+str(len(feedbacks))+
           ", вопросы без ответа — "+str(len(questions))+
           ". Данные обновлены в Streamlit; ответы публикуются после вашего подтверждения.")

def queue():
    from review_queue import process_due
    import process_telegram_jobs as jobs
    # Stock retries run here using the existing atomic claim, without dispatching
    # another private-repository Actions job.
    jobs.runtime_state.dispatch_due_stock=lambda: {"status":"handled_by_public_runner"}
    process_due(limit=10)
    asyncio.run(jobs.main())
    claim=jobs.db("POST","/rpc/claim_stock_retry",payload={"p_key":"stock-retry"})
    if claim:
        success=False
        try:
            os.environ["AUTO_STOCK_RETRY"]="true"
            validate_stock()
            execute("Run deferred stock verification",["auto_stock_runner.py"])
            success=True
        finally:
            # Only finish the original claim. The private writer may have saved a
            # new retry, which must remain intact.
            jobs.db("POST","/rpc/finish_stock_retry_dispatch",
                    payload={"p_claim":claim["claim"],"p_success":success})

def main(task):
    if task not in {"reviews","advertising","stock","analytics","finance","queue","probe"}:
        raise ValueError("Unknown task")
    for key,value in list(os.environ.items()):
        if key.startswith(("WB_","SUPABASE_","TELEGRAM_","ADVERTISING_","MOYSKLAD_")):
            os.environ[key]=value.strip()
    os.environ["WB_FEEDBACK_TOKEN"]=os.environ.get("WB_FEEDBACK_TOKEN") or os.environ.get("WB_TOKEN_1","")
    os.chdir(SOURCE)
    sys.path.insert(0,str(SOURCE))
    if task=="probe":
        execute("Validate private source",["-m","py_compile","auto_stock.py","process_review_queue.py",
              "process_telegram_jobs.py","advertising_agent/notify.py"])
        execute("Validate stock safeguards",["-m","unittest","discover","-s","tests"])
        import select_task
        hidden(select_task.queue_due)
        import requests
        for slug in ("telegram-webhook","stock-retry-dispatch"):
            r=requests.post(os.environ["SUPABASE_URL"].rstrip("/")+"/functions/v1/"+slug,json={},timeout=(5,20))
            if r.status_code!=401:
                raise RuntimeError("Unauthenticated webhook was not rejected")
        print("Source, safeguards, queue access and webhook authentication verified.")
    elif task=="reviews":
        hidden(reviews)
    elif task=="queue":
        hidden(queue)
    elif task=="advertising":
        execute("Validate advertising logic",["-m","unittest","discover","-s","tests","-p","test_advertising_decision_engine.py"])
        execute("Validate advertising experiments",["-m","unittest","discover","-s","tests","-p","test_advertising_experiments.py"])
        execute("Validate product economics",["-m","unittest","discover","-s","tests","-p","test_sku_economics.py"])
        execute("Collect advertising context",["advertising_agent/collect_ip.py"])
        execute("Refresh economics from cache",["advertising_agent/sku_economics.py","--refresh-from-cache"],optional=True)
        execute("Build recommendations",["advertising_agent/decision_engine.py"])
        execute("Analyze low CTR photos",["advertising_agent/photo_ctr_analysis.py"],optional=True)
        execute("Refresh advertising experiments",["advertising_agent/experiments.py"])
        execute("Send advertising report",["advertising_agent/notify.py"])
    elif task=="stock":
        validate_stock()
        os.environ["AUTO_STOCK_RETRY"]=os.environ.get("REQUESTED_RETRY","false")
        execute("Allocate and verify stock",["auto_stock_runner.py"])
    elif task=="analytics":
        execute("Refresh daily supporting analytics",["analytics/collect.py"])
    elif task=="finance":
        execute("Refresh daily product economics",["advertising_agent/sku_economics.py"])
    print("Task complete.",flush=True)

if __name__=="__main__":
    task=sys.argv[1] if len(sys.argv)>1 else "probe"
    try:
        main(task)
    except Exception as exc:
        import traceback
        if str(exc)!="Private task failed":
            save_diagnostic(task,traceback.format_exc())
        print("Task failed: "+type(exc).__name__+". Business output is kept private.",flush=True)
        try:
            hidden(lambda: notify("⚠️ Задание «"+task+"» в новом GitHub не завершено. Проверьте статус запуска; отсутствующие данные не считаются нулевыми.",task in {"advertising","finance"}))
        except Exception:
            print("Failure notification unavailable.",flush=True)
        raise SystemExit(1)
