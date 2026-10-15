"""Owner-authorized review recovery: WB GET only, six CAS closures and fresh inbox."""
import os,json,time,hashlib,contextlib,io
from datetime import datetime,timezone,timedelta
from stock_deploy_support import seal,error
import review_queue as q
import wildberries as wb
from review_scope import parse_reply_key,inbox_key
from review_inbox_cache import load_inbox,save_inbox
from refresh_review_inbox import fresh_today
IDS=['rDNbPMXeKeasOL5AumVm','7XnbBoUub7p6RzYjbnCT','veschi-review:token_2:feedbacks:pfmEvEUwQTiS1Swm3uq1','veschi-review:token_2:questions:F1bfL6EBACfpILHUJeH2','veschi-review:token_2:feedbacks:ANHXGhh56fEF75Pv5516','veschi-review:token_2:feedbacks:0AVw0CpKLnHd1KO7JUVe']
def sha(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def persist(key,payload):
    now=datetime.now(timezone.utc)
    q._request('POST','/telegram_api_cache',params={'on_conflict':'cache_key'},payload={'cache_key':key,'payload':payload,'updated_at':now.isoformat(),'expires_at':(now+timedelta(days=3650)).isoformat()},prefer='resolution=ignore-duplicates,return=minimal')
    rows=q._request('GET','/telegram_api_cache',params={'cache_key':'eq.'+key,'select':'payload','limit':1}) or []
    if not rows or sha(rows[0]['payload'])!=sha(payload):raise RuntimeError('History readback mismatch')
DEADLINE=time.monotonic()+8*60

def wait_scope(cabinet):
    pause=wb.review_pause_seconds(cabinet=cabinet)
    if pause>90 or time.monotonic()+pause+30>DEADLINE:raise wb.ReviewRateLimit(max(pause,1))
    if pause>0:time.sleep(pause+1)
def main():
    report={'manual':[],'inboxes':[],'wb_writes':0,'telegram_sends':0}
    for key in IDS:
        result={'key':key};report['manual'].append(result)
        try:
            rows=q._request('GET','/review_replies',params={'feedback_id':'eq.'+key,'select':'*','limit':1}) or []
            if len(rows)!=1:raise RuntimeError('Missing review row')
            before=rows[0]
            if before['state']=='sent' and str(before.get('error','')).startswith('MANUAL_CONFIRMED:'):
                result['status']='already_closed';continue
            if before['state']!='needs_check':raise RuntimeError('Unexpected state; no mutation')
            cabinet,kind,item=parse_reply_key(key)
            wait_scope(cabinet)
            actual=wb.get_reply_answer(item,kind,cabinet=cabinet)
            if not actual.strip():result['status']='no_answer_verified';continue
            receipt={'before':before,'observed_at':datetime.now(timezone.utc).isoformat(),'actual_answer_sha256':hashlib.sha256(actual.encode()).hexdigest(),'actual_answer':actual,'mode':'manual_confirmed'}
            persist('reviews:manual-history:'+sha(key)+':'+sha(receipt),receipt)
            marker='MANUAL_CONFIRMED: '+receipt['observed_at']+' sha256='+receipt['actual_answer_sha256']
            updated=q._request('PATCH','/review_replies',params={'feedback_id':'eq.'+key,'state':'eq.needs_check','answer':'eq.'+before['answer'],'error':'eq.'+str(before.get('error') or '')},payload={'state':'sent','retry_at':0,'error':marker},prefer='return=representation')
            after=q._request('GET','/review_replies',params={'feedback_id':'eq.'+key,'select':'*','limit':1}) or []
            if not updated or not after or after[0]['state']!='sent' or after[0]['answer']!=before['answer'] or after[0]['error']!=marker:raise RuntimeError('Manual closure not confirmed')
            result.update(status='manual_confirmed',answer_preserved=True,history_readback=True,row_readback=True)
        except wb.ReviewRateLimit as exc:result.update(status='paused',retry_after=exc.retry_seconds)
        except Exception as exc:result.update(status='error',error=error(exc))
        finally:seal('reviews-recovery',report)
    for cabinet in ('token_1','token_2','token_3'):
        for kind,fetch in (('feedbacks',wb.get_unanswered_feedbacks),('questions',wb.get_unanswered_questions)):
            result={'cabinet':cabinet,'kind':kind};report['inboxes'].append(result)
            try:
                cached,stamp=load_inbox(kind,cabinet=cabinet)
                if cached is not None and fresh_today(stamp):
                    result.update(status='fresh_cache',count=len(cached),fetched_at=stamp);continue
                items=[];skip=0;complete=False
                for page in range(10):
                    wait_scope(cabinet)
                    rows=fetch(take=100,skip=skip,cabinet=cabinet)
                    items.extend(rows);skip+=len(rows)
                    if len(rows)<100:complete=True;break
                if not complete:raise RuntimeError('Pagination cap; previous complete inbox retained')
                items=list({str(r['id']):r for r in items if r.get('id')}.values())
                save_inbox(kind,items,cabinet=cabinet)
                observed,stamp=load_inbox(kind,cabinet=cabinet)
                if sha(items)!=sha(observed):raise RuntimeError('Inbox full payload readback mismatch')
                result.update(status='complete',count=len(items),fetched_at=stamp,full_sha256=sha(items),readback=True,items=items)
            except wb.ReviewRateLimit as exc:result.update(status='paused',retry_after=exc.retry_seconds)
            except Exception as exc:result.update(status='error',error=error(exc))
            finally:seal('reviews-recovery',report)
    report['manual_history']=q._request('GET','/telegram_api_cache',params={'cache_key':'like.reviews:manual-history:*','select':'cache_key,payload','limit':100}) or []
    return report
hidden=io.StringIO()
try:
    with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):report=main()
except BaseException as exc:report={'error':error(exc)}
report['private_log']=hidden.getvalue()
path=seal('reviews-recovery',report)
print(json.dumps({'manual_closed':sum(x.get('status')=='manual_confirmed' for x in report.get('manual',[])),'inbox_complete':sum(x.get('status') in ('complete','fresh_cache') for x in report.get('inboxes',[])),'wb_writes':0,'telegram_sends':0}))

# Sequential continuation after saved WB RetryAfter, 2026-10-15T09:49UTC.

# Resume only missing IP inboxes after 2026-10-15T10:01:56UTC RetryAfter.
