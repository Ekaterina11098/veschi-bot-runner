"""One renewed exact646 attempt. No old queues, other reviews or Telegram calls."""
import os,sys,json,time,copy
from pathlib import Path
import psycopg,wildberries
from review_telegram_approval import Approval,Repository,sha
from review_approval_bridge import SQLSource,DurableBridge
from review_telegram_runtime import CanonicalGuard
from review_approval_executor import WBAdapter
from review_approval_backup import snapshot,encrypt
sys.path.insert(0,str(Path(__file__).resolve().parent))
from review_646_controlled_retry import Retry,INTENT,AUTH
conn=psycopg.connect(os.environ['REVIEW_APPROVAL_DSN'],autocommit=True,connect_timeout=15,options='-c statement_timeout=30000')
repo=Repository(conn,postgres=True)
a=Approval(repo,os.environ['REVIEW_APPROVAL_INGRESS_KEY'],os.environ['REVIEW_APPROVAL_OWNER_ID'],os.environ['TELEGRAM_ALLOWED_CHAT_ID'],os.environ['REVIEW_APPROVAL_BOT_ID'],enabled=True)
bridge=DurableBridge(a,SQLSource(conn))
out=Path(os.environ['RUNNER_TEMP'])/'review-approval-output';out.mkdir(exist_ok=True)
last_good=None;retry=None;fatal=None
def preserve():
    global last_good
    try:
        data=snapshot(repo);last_good=copy.deepcopy(data)
    except Exception as exc:
        if last_good is None:raise
        data=copy.deepcopy(last_good);data['snapshot_fallback_error_type']=type(exc).__name__
    data['controlled_retry_http_diagnostic']=copy.deepcopy(retry.http_buffer if retry else [])
    data['controlled_retry_authorization']=AUTH
    data['fatal_error_type']=fatal
    sealed=encrypt(data,os.environ['RECOVERY_PUBLIC_KEY'].encode())
    target=out/'approval-supplement.aes.json';temporary=out/'approval-supplement.tmp'
    temporary.write_text(json.dumps(sealed));temporary.replace(target)
try:
    conn.execute("SELECT pg_advisory_lock(hashtextextended('review-approval-process-ui-v1',0))")
    baseline=snapshot(repo)
    adapter=WBAdapter(wildberries)
    retry=Retry(a,adapter,CanonicalGuard(a,bridge.project),preserve)
    retry.initialize()
    from urllib.parse import urlsplit
    import requests
    undo=retry.install_http_journal(requests,urlsplit(os.environ['SUPABASE_URL']).hostname)
    deadline=time.monotonic()+29*60
    while time.monotonic()<deadline:
        result=retry.step()
        if result['status']=='rejected':
            result=retry.verify_rejection()
            if result.get('rejection_checked_at') or result.get('rejection_read_needs_diagnosis'):break
        elif result['status'] in ('confirmed','manual_present','needs_diagnosis','blocked'):break
        delay=max(0,result.get('wait_seconds',0),0 if result['status']=='rejected' else result.get('not_before',0)-time.time(),adapter.pause('token_1'))
        if delay<=0:raise RuntimeError('Recovery did not make a durable transition')
        preserve()
        if time.monotonic()+delay+45>deadline:break
        until=time.monotonic()+delay+1
        while time.monotonic()<until:time.sleep(min(45,until-time.monotonic()))
    after=snapshot(repo)
    for key in ('source_cache','source_journal'):
        if baseline['manifest'][key]!=after['manifest'][key]:raise RuntimeError('Untargeted source state changed')
    current=repo.get('intents',INTENT);operation=repo.get('events',AUTH)
    print(json.dumps({'publication_status':current['status'],'controlled_retry_status':operation['status'],
        'post_consumed':operation['post_consumed'],'http_post_started':operation['http_post_started'],
        'post_http_status':operation.get('post_http_status'),
        'readback_confirmed':current.get('actual_answer_sha256')==operation['answer_sha256'],
        'telegram_calls':0,'other_source_state_unchanged':True}))
except Exception as exc:
    fatal=type(exc).__name__
    print(json.dumps({'completed':False,'error_type':fatal,'telegram_calls':0}))
finally:
    try:preserve()
    finally:conn.close()
if fatal:raise SystemExit(1)
