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
            if name.startswith(("WB_","SUPABASE_","TELEGRAM_","ADVERTISING_","CHINA_","BUSINESS_","MOYSKLAD_","OPENAI_","MPSTATS_")) and len(value)>=6:
                text=text.replace(value,"[redacted]")
        key=os.environ["SUPABASE_SECRET_KEY"]
        headers={"apikey":key,"Content-Type":"application/json","Prefer":"resolution=merge-duplicates"}
        if not key.startswith("sb_secret_"):
            headers["Authorization"]="Bearer "+key
        now=datetime.now(timezone.utc)
        response=requests.post(os.environ["SUPABASE_URL"].rstrip("/")+"/rest/v1/telegram_api_cache?on_conflict=cache_key",
            headers=headers,json={"cache_key":"runner:diagnostic:"+os.environ.get("GITHUB_RUN_ID","manual")+":"+os.environ.get("TASK","manual"),
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
            if name.startswith(("WB_","SUPABASE_","TELEGRAM_","ADVERTISING_","CHINA_","BUSINESS_","MOYSKLAD_","AUTO_STOCK_","OPENAI_","MPSTATS_")):
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
    from refresh_review_inbox import refresh_all
    results=refresh_all()
    names={'token_1':'ООО','token_2':'ИП','token_3':'Китай'}
    lines=['📩 Проверка отзывов и вопросов']
    for cabinet,result in results.items():
        counts=result['counts']
        lines.append(names[cabinet]+': отзывы — '+str(counts.get('feedbacks','не получены'))+
                     ', вопросы — '+str(counts.get('questions','не получены'))+
                     ('. Проверка неполная; повтор сохранён.' if result['errors'] else '. Данные обновлены.'))
    notify('\n'.join(lines))

def review_queue():
    from review_queue import process_due
    process_due(limit=10)

def telegram_queue():
    import process_telegram_jobs as jobs
    # Stock retries have their own worker and stock concurrency group.
    jobs.runtime_state.dispatch_due_stock=lambda: {"status":"handled_by_public_runner"}
    asyncio.run(jobs.main())

def stock_retry():
    from wb_runtime_state import db
    claim=db("POST","/rpc/claim_stock_retry",payload={"p_key":"stock-retry"})
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
            db("POST","/rpc/finish_stock_retry_dispatch",
                    payload={"p_claim":claim["claim"],"p_success":success})

def queue():
    # Compatibility for older workflow callers; every component gets a process.
    failed = False
    for task in ("review_queue", "telegram_queue", "stock_retry", "business_agent"):
        result = subprocess.run([sys.executable, str(ROOT/"run_private.py"), task],
                                env={**os.environ, "TASK":task})
        failed = failed or bool(result.returncode)
    if failed:
        raise RuntimeError("Private task failed")

def main(task):
    if task not in {"daily_validation","daily_context","reviews","advertising","stock","analytics","finance","queue","probe",
                    "review_queue","telegram_queue","stock_retry","advertising_report_retry","agent","business_agent","finance_retry","advertising_research","mpstats_recovery","analytics_recovery","budget_retry","review_inbox_retry"}:
        raise ValueError("Unknown task")
    for key,value in list(os.environ.items()):
        if key.startswith(("WB_","SUPABASE_","TELEGRAM_","ADVERTISING_","CHINA_","BUSINESS_","MOYSKLAD_","OPENAI_","MPSTATS_")):
            os.environ[key]=value.strip()
    os.environ["WB_FEEDBACK_TOKEN"]=os.environ.get("WB_FEEDBACK_TOKEN") or os.environ.get("WB_TOKEN_1","")
    os.chdir(SOURCE)
    sys.path.insert(0,str(SOURCE))
    if task=="daily_validation":
        execute("Compile completed-day modules",["-m","compileall","-q","analytics","advertising_agent","stock_daily_data.py","stock_mpstats.py","tg_agent_new.py"])
        for pattern in ("test_daily_data.py","test_advertising_decision_engine.py","test_advertising_experiments.py",
                        "test_sku_economics.py","test_wb_sources.py","test_analytics_warehouse.py","test_finance_daily.py",
                        "test_auto_stock.py","test_stock_limits.py","test_sales_cache.py","test_mpstats*.py","test_source_collection_policy.py"):
            execute("Validate daily data: "+pattern,["-m","unittest","discover","-s","tests","-p",pattern])
    elif task=="probe":
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
    elif task=="agent":
        execute("Process advertising conversations",["-m","advertising_agent.conversation"])
    elif task=="business_agent":
        execute("Process isolated business conversations",["-m","business_agents.conversation"])
    elif task=="reviews":
        hidden(reviews)
    elif task=="queue":
        hidden(queue)
    elif task=="review_inbox_retry":
        from refresh_review_inbox import refresh_all
        hidden(refresh_all)
    elif task=="review_queue":
        hidden(review_queue)
    elif task=="telegram_queue":
        hidden(telegram_queue)
    elif task=="stock_retry":
        hidden(stock_retry)
    elif task=="advertising":
        execute("Validate advertising logic",["-m","unittest","discover","-s","tests","-p","test_advertising_decision_engine.py"])
        execute("Validate advertising experiments",["-m","unittest","discover","-s","tests","-p","test_advertising_experiments.py"])
        execute("Validate product economics",["-m","unittest","discover","-s","tests","-p","test_sku_economics.py"])
        execute("Collect advertising context",["advertising_agent/collect_ip.py"])
        execute("Review complete advertising costs and historical conversion",["-m","analytics.campaign_review"],optional=True)
        execute("Refresh economics from cache",["advertising_agent/sku_economics.py","--refresh-from-cache"],optional=True)
        execute("Build recommendations",["advertising_agent/decision_engine.py"])
        execute("Analyze low CTR photos",["advertising_agent/photo_ctr_analysis.py"],optional=True)
        execute("Refresh advertising experiments",["advertising_agent/experiments.py"])
        execute("Send advertising report",["advertising_agent/notify.py"])
    elif task=="advertising_report_retry":
        import select_task
        target=select_task.evening_target_date()
        if target:
            os.environ["ADVERTISING_EVENING_RECOVERY_DATE"]=target
            execute("Restore missing evening advertising report",["advertising_agent/notify.py"])
    elif task=="stock":
        validate_stock()
        os.environ["AUTO_STOCK_RETRY"]=os.environ.get("REQUESTED_RETRY","false")
        execute("Allocate and verify stock",["auto_stock_runner.py"])
    elif task=="analytics":
        execute("Prepare shared completed-day analytics and stock demand",["-m","analytics.daily_prepare"])
    elif task=="daily_context":
        execute("Validate shared daily windows",["-m","unittest","discover","-s","tests","-p","test_daily_data.py"])
        execute("Collect complete advertising and price history",["-m","analytics.campaign_review"],optional=True)
        execute("Prepare advertising daily context from shared data",["advertising_agent/collect_ip.py"])
        execute("Refresh economics from daily cache",["advertising_agent/sku_economics.py","--refresh-from-cache"],optional=True)
    elif task=="budget_retry":
        from advertising_agent import collect_ip
        token=os.environ.get("WB_TOKEN_2")
        if not token:raise RuntimeError("WB_TOKEN_2 is missing")
        _,active_ids,_,_=collect_ip.campaign_index(token)
        collect_ip.collect_campaign_budgets(token,active_ids)
    elif task=="analytics_recovery":
        execute("Recover missing exact-period analytics",["-m","analytics.data_recovery"])
    elif task=="mpstats_recovery":
        execute("Validate source collection priority",["-m","unittest","discover","-s","tests","-p","test_source_collection_policy.py"])
        execute("Validate MPSTATS source recovery",["-m","unittest","discover","-s","tests","-p","test_mpstats*.py"])
        execute("Recover missing analytics through MPSTATS",["-m","analytics.mpstats_gaps"])
    elif task=="advertising_research":
        import select_task
        if select_task.finance_retry_work() or select_task.budget_work():
            print("WB-only finance/budget work has priority; optional review remains queued.",flush=True)
            return
        execute("Validate free advertising sources",["-m","unittest","discover","-s","tests","-p","test_wb_sources.py"])
        execute("Analyze IP and OOO campaigns without WB changes",["-m","analytics.campaign_review"])
    elif task=="finance_retry":
        import select_task
        # Recheck after acquiring the shared finance/advertising lock.
        if select_task.finance_retry_work():
            execute("Resume saved daily Finance cursors",["-m","analytics.finance_daily"])
            execute("Build product economics from complete daily reports",["advertising_agent/sku_economics.py"],optional=True)
    elif task=="finance":
        execute("Validate daily Finance top-up",["-m","unittest","discover","-s","tests","-p","test_finance_daily.py"])
        execute("Validate SKU economics",["-m","unittest","discover","-s","tests","-p","test_sku_economics.py"])
        execute("Validate China daily Finance integration",["-m","unittest","discover","-s","tests","-p","test_china_sales_demand.py"])
        execute("Collect missing daily Finance reports",["-m","analytics.finance_daily"])
        execute("Build product economics from complete daily reports",["advertising_agent/sku_economics.py"],optional=True)
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
            # Failed evening delivery is retried by the queue; do not spam the chat.
            if task not in {"daily_validation","advertising_report_retry","agent","business_agent","mpstats_recovery"}:
                hidden(lambda: notify("⚠️ Задание «"+task+"» в новом GitHub не завершено. Проверьте статус запуска; отсутствующие данные не считаются нулевыми.",task in {"advertising","finance"}))
        except Exception:
            print("Failure notification unavailable.",flush=True)
        raise SystemExit(1)
