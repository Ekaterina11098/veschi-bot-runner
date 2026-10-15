"""One authorized exact review publication; durable write intent and WB readback, no queue drain."""
import os,time,json,contextlib,io
from datetime import datetime,timezone
from stock_deploy_support import seal,error
from review_queue import _request,enqueue
from review_durable_workflow import DurableReviews,digest
import wildberries as wb
STORE=DurableReviews(_request)
KEY='reviews:publication:token_1:soHH5MsaEY08FASqdqtM:owner-v2'
INPUT='reviews:publication-input:token_1:soHH5MsaEY08FASqdqtM:owner-v2'
ID='soHH5MsaEY08FASqdqtM'
report={'wb_write_attempts':0,'telegram_sends':0,'target':ID}
def checkpoint():seal('review-publication',report)
def save(state):
    now=datetime.now(timezone.utc).isoformat()
    _request('POST','/telegram_api_cache',params={'on_conflict':'cache_key'},payload={'cache_key':KEY,'payload':state,'updated_at':now,'expires_at':'9999-12-31T00:00:00Z'},prefer='resolution=merge-duplicates,return=minimal')
    if STORE.read(KEY)!=state:raise RuntimeError('Publication state readback failed')
    report['state']=state;checkpoint()
def pause():
    seconds=wb.review_pause_seconds(cabinet='token_1')
    if seconds>90:
        report['retry_after']=seconds;return False
    if seconds:time.sleep(seconds+2)
    return True
def main():
    data=STORE.read(INPUT)
    if not data or data.get('approved_variant')!=1 or data.get('cabinet')!='token_1' or data.get('item_id')!=ID:raise RuntimeError('Exact authorization missing')
    hold=STORE.read('reviews:hold:token_1:feedbacks:'+ID)
    if hold and hold.get('active'):raise RuntimeError('Target held')
    ish=STORE.read('reviews:hold:token_2:feedbacks:PwB5eXmFztbgyBhGctsP')
    if not ish or ish.get('active') is not True:raise RuntimeError('Ishkhan hold missing')
    cached,_=__import__('review_inbox_cache').load_inbox('feedbacks',cabinet='token_1')
    items=[i for i in cached or [] if str(i.get('id'))==ID]
    if len(items)!=1:raise RuntimeError('Source item missing')
    STORE.save_variants(items[0],'token_1','feedbacks',data['variants'],data['version'])
    approval=STORE.approve('token_1','feedbacks',ID,data['version'],1,True)
    answer=data['variants'][1]
    if approval['answer_sha256']!=digest(answer):raise RuntimeError('Approval text mismatch')
    report['input']=data;report['approval']=approval
    state=STORE.read(KEY) or {'phase':'preflight','authorized_sha256':digest(answer)}
    if state.get('authorized_sha256')!=digest(answer):raise RuntimeError('Publication text changed')
    if state['phase'] in ('confirmed','manual_present','needs_check'):report['state']=state;return
    if state['phase']=='ready' and time.time()-state['preflight_at']>1800:
        # Refresh only a PROVEN rejected write, never an ambiguous or accepted POST.
        rows=_request('GET','/review_replies',params={'feedback_id':'eq.'+ID,'select':'state,error,answer','limit':1}) or []
        if state.get('last_explicit_rejection')!='HTTP429' or state.get('post_http_accepted') or not rows or rows[0]['state']!='pending' or rows[0]['error']!='WB_READY: explicit HTTP429 rejection' or rows[0]['answer']!=answer:
            raise RuntimeError('Expired preflight cannot be safely renewed')
        state.update(phase='preflight',previous_preflight_at=state['preflight_at'],preflight_renewal_reason='proven_HTTP429_rejection_no_unknown')
        save(state)
    if state['phase']=='preflight':
        if not pause():return
        actual=wb.get_reply_answer(ID,'feedbacks',cabinet='token_1')
        if actual.strip():
            state.update(phase='confirmed' if actual.strip()==answer.strip() else 'manual_present',actual_answer=actual,observed_at=datetime.now(timezone.utc).isoformat())
            save(state);return
        row=enqueue(ID,answer,cabinet='token_1',kind='feedbacks')
        if row.get('state')!='pending':raise RuntimeError('Unexpected existing review queue state')
        state.update(phase='ready',preflight_at=time.time())
        save(state)
    if state['phase']=='ready':
        if time.time()-state['preflight_at']>1800:raise RuntimeError('Preflight expired; requires reconciliation')
        if not pause():return
        # Any ambiguous transport outcome after this point permits reads ONLY.
        state.update(phase='verify',write_intent_at=time.time())
        save(state)
        row=_request('PATCH','/review_replies',params={'feedback_id':'eq.'+ID,'state':'eq.pending','answer':'eq.'+answer},payload={'state':'sending','error':'WB_VERIFY:'+str(int(time.time()))+': owner exact version2'},prefer='return=representation')
        if not row:raise RuntimeError('Exact review write claim failed')
        try:
            report['wb_write_attempts']+=1
            wb.post_review_reply(ID,answer,cabinet='token_1')
            state['post_http_accepted']=True;save(state)
        except wb.ReviewRateLimit as exc:
            state.update(phase='ready',last_explicit_rejection='HTTP429',retry_after=exc.retry_seconds)
            _request('PATCH','/review_replies',params={'feedback_id':'eq.'+ID,'state':'eq.sending','answer':'eq.'+answer},payload={'state':'pending','error':'WB_READY: explicit HTTP429 rejection','retry_at':int(time.time())+exc.retry_seconds},prefer='return=representation')
            save(state);report['retry_after']=exc.retry_seconds;return
        except Exception as exc:report['write_error']=error(exc)
    if state['phase']=='verify':
        if not pause():return
        actual=wb.get_reply_answer(ID,'feedbacks',cabinet='token_1')
        report['actual_answer']=actual
        if actual.strip()==answer.strip():
            changed=_request('PATCH','/review_replies',params={'feedback_id':'eq.'+ID,'answer':'eq.'+answer,'state':'in.(pending,sending)'},payload={'state':'sent','error':'WB_CONFIRMED: owner revised version2','retry_at':0},prefer='return=representation')
            rows=_request('GET','/review_replies',params={'feedback_id':'eq.'+ID,'select':'*','limit':1}) or []
            if not changed or not rows or rows[0]['state']!='sent' or rows[0]['answer']!=answer:raise RuntimeError('Final queue readback failed')
            state.update(phase='confirmed',confirmed_at=datetime.now(timezone.utc).isoformat(),actual_answer=actual)
            report['journal_readback']=True;save(state)
        elif actual.strip():
            state.update(phase='needs_check',actual_answer=actual);save(state)
        else:
            state['verification_empty_at']=datetime.now(timezone.utc).isoformat();save(state)
hidden=io.StringIO()
try:
    with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):main()
except wb.ReviewRateLimit as exc:report['retry_after']=exc.retry_seconds
except Exception as exc:report['error']=error(exc)
finally:
    try:
        report['durable_backup']=_request('GET','/telegram_api_cache',params={'cache_key':'like.reviews:*','select':'*','limit':2000})
        report['review_row']=_request('GET','/review_replies',params={'feedback_id':'eq.'+ID,'select':'*'})
    except Exception as exc:report['backup_error']=error(exc)
    report['private_log']=hidden.getvalue();checkpoint()
    print(json.dumps({'phase':report.get('state',{}).get('phase'),'retry_after':report.get('retry_after'),'wb_write_attempts':report['wb_write_attempts'],'error_type':report.get('error',{}).get('type')}))
