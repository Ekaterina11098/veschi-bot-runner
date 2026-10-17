"""One owner-approved retained content-preparation message. No collection, WB, content publication."""
import os,sys,json,copy,hashlib,runpy
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.parse import urlparse
import requests
sys.path.insert(0,str(Path.cwd()))
sys.path.insert(0,str(Path.cwd()/'tests'))
sys.path.insert(0,str(Path.cwd().parent))
from stock_deploy_support import seal
BATCH='content-209-600-20261017-v1'
EXPECTED={'347406432:39410834:content_brief','776196396:39410834:content_brief'}
proof=dict(batch=BATCH,wb_writes=0,source_calls=0,content_publications=0,telegram_calls=0,decoded_bytes=0,complete=False,automatic_retry=False)
native=requests.sessions.Session.request
allowed=urlparse(os.environ['SUPABASE_URL']).hostname
def guard(session,method,url,*args,**kwargs):
    parsed=urlparse(str(url))
    if parsed.hostname==allowed and parsed.path.startswith('/rest/v1/'):
        if method.upper() not in ('GET','POST','PATCH'):raise RuntimeError('Unsupported state method')
    elif parsed.hostname=='api.telegram.org' and parsed.path.endswith('/sendMessage') and method.upper()=='POST':
        if proof['telegram_calls']>=1:raise RuntimeError('One Telegram request only')
        proof['telegram_calls']+=1
    else:raise RuntimeError('Source or WB transport forbidden')
    response=native(session,method,url,*args,**kwargs)
    proof['decoded_bytes']+=len(response.content)
    if proof['decoded_bytes']>100_000_000:raise RuntimeError('100MB limit')
    return response
requests.sessions.Session.request=guard
try:
    from analytics import ip_daily_recommendations as d
    from advertising_agent import agent_store as store
    from advertising_agent.notify import db,S
    now=datetime.now(timezone.utc)
    if now.astimezone(d.ZoneInfo('Europe/Moscow')).date().isoformat()!='2026-10-17':raise RuntimeError('Expired one-message authorization')
    registration=store.registration()
    approval=store.cache_get('advertising:ip:limited_rollout:v1') or {}
    if not (approval.get('owner_id')==registration['registered_by_user_id'] and approval.get('chat_id')==registration['chat_id'] and approval.get('policy_version')==d.POLICY_VERSION):
        raise RuntimeError('Existing registered owner approval mismatch')
    receipt_key='advertising:ip:delivery-receipt:'+BATCH
    prior_receipt=store.cache_get(receipt_key)
    if prior_receipt and prior_receipt.get('ok') is True:
        proof.update(complete=True,status='already_confirmed_no_send',receipt=prior_receipt)
    else:
        namespace=runpy.run_path('tests/test_ip_full_offline_pipeline.py')
        generated=namespace['retained_pair_preview_acceptance']()
        actions=generated['generated_actions']
        if {a['key'] for a in actions}!=EXPECTED:raise RuntimeError('Unexpected recommendation scope')
        def state_row():
            rows=db('GET','telegram_api_cache',params={'cache_key':'eq.'+d.KEY,'select':'payload,updated_at','limit':1}) or []
            if len(rows)!=1:raise RuntimeError('Canonical recommendation state missing')
            return rows[0]
        baseline=state_row()
        scoped_previous=copy.deepcopy(baseline['payload'])
        scoped_previous['records']={k:v for k,v in scoped_previous.get('records',{}).items() if k in EXPECTED}
        source_fixture=json.loads(Path('tests/fixtures/ip_pair_preview_retained_20261017.json').read_text(encoding='utf-8'))
        pairs=[dict(pair_key=a['pair_key'],article=a['article'],campaign_id=a['campaign_id'],nm_id=a['nm_id'],facts=a['facts']) for a in actions]
        scoped_state=d.reconcile(scoped_previous,actions,pairs,source_fixture['report'],now)
        if set(scoped_state['records'])!=EXPECTED:raise RuntimeError('Unexpected registered keys')
        report=dict(cabinet='token_2',policy_version=d.POLICY_VERSION,message_format='drr_action_v1',
            period_from='2026-10-10',period_to='2026-10-16',observed_at=now.isoformat(),
            wb_writes_enabled=False,all_active_campaigns_assessed=False,decision_state=scoped_state)
        messages=d.render_campaign_messages(report)
        if len(messages)!=1 or set(messages[0]['record_keys'])!=EXPECTED:raise RuntimeError('Expected exactly one new two-item message')
        text=messages[0]['text']
        if len(text)>4000 or any(x in text for x in ('nm347','nm776','2026-10-','SHA')):raise RuntimeError('Short format validation failed')
        text_sha=hashlib.sha256(text.encode()).hexdigest()
        consent=copy.deepcopy(approval);consent['telegram_delivery_approved']=True
        consent['explicit_delivery_scope']=dict(campaign_id=39410834,record_keys=sorted(EXPECTED),
            period_from=report['period_from'],period_to=report['period_to'],preparation_only=True,text_sha256=text_sha,
            owner_instruction='Explicit owner authorization in current chat, 2026-10-17; one message with 209 and 600')
        proof.update(period_from=report['period_from'],period_to=report['period_to'],text=text,text_sha256=text_sha,generated_actions=actions)
        holder={'expected':{k:copy.deepcopy(baseline['payload'].get('records',{}).get(k)) for k in EXPECTED}}
        def save_state(scoped):
            current=state_row()
            for key in EXPECTED:
                if current['payload'].get('records',{}).get(key)!=holder['expected'][key]:
                    raise RuntimeError('Concurrent scoped recommendation change; stop without overwriting')
            merged=copy.deepcopy(current['payload'])
            for key in EXPECTED:merged.setdefault('records',{})[key]=copy.deepcopy(scoped['records'][key])
            merged.update(policy_version=d.POLICY_VERSION,observed_at=datetime.now(timezone.utc).isoformat())
            stamp=datetime.now(timezone.utc).isoformat()
            params={'cache_key':'eq.'+d.KEY,'updated_at':('eq.'+current['updated_at']) if current.get('updated_at') else 'is.null','select':'payload,updated_at'}
            saved=db('PATCH','telegram_api_cache',params=params,body={'payload':merged,'updated_at':stamp},prefer='return=representation') or []
            if len(saved)!=1:raise RuntimeError('Recommendation CAS conflict; no blind retry')
            readback=state_row()
            if readback['payload']!=merged:raise RuntimeError('Recommendation save readback mismatch')
            holder['expected']={k:copy.deepcopy(merged['records'][k]) for k in EXPECTED}
        def send_one(chat,message):
            if message!=text or chat!=registration['chat_id']:raise RuntimeError('Exact approved message or chat mismatch')
            response=S.post('https://api.telegram.org/bot'+os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()+'/sendMessage',json={'chat_id':chat,'text':message},timeout=(10,30))
            if response.status_code==429:
                wait=(response.json().get('parameters') or {}).get('retry_after')
                if type(wait) in (int,float) and wait>0:raise d.DeliveryRateLimited(datetime.now(timezone.utc)+timedelta(seconds=wait))
            if response.status_code!=200:raise RuntimeError('Telegram HTTP not confirmed')
            body=response.json();msg=body.get('result') or {}
            receipt=dict(ok=body.get('ok') is True,message_id=msg.get('message_id'),chat_id=(msg.get('chat') or {}).get('id'),text_sha256=text_sha,at=datetime.now(timezone.utc).isoformat(),batch=BATCH)
            proof['receipt']=receipt
            if not receipt['ok'] or type(receipt['message_id']) is not int or receipt['chat_id']!=chat:raise RuntimeError('Telegram receipt mismatch')
            store.cache_set(receipt_key,receipt,ttl_days=365)
            if store.cache_get(receipt_key)!=receipt:raise RuntimeError('Receipt storage readback mismatch')
            return receipt
        delivery=d.approved_delivery(report,registration,consent,True,send_one,save_state,now)
        proof['delivery']=delivery
        final=state_row()['payload']
        proof['saved_recommendations']={k:final['records'][k] for k in EXPECTED if k in final.get('records',{})}
        if delivery.get('sent')!=1 or delivery.get('failures'):raise RuntimeError('One-message delivery incomplete; do not retry automatically')
        receipt=proof['receipt']
        if not all(final['records'][k].get('delivery_receipt',{}).get('message_id')==receipt['message_id'] and not final['records'][k].get('delivery_uncertain') and final['records'][k].get('stage')=='proposed' for k in EXPECTED):raise RuntimeError('Canonical delivery receipt mismatch')
        tomorrow=copy.deepcopy(report);tomorrow['observed_at']=(now+timedelta(days=1)).isoformat()
        for rec in tomorrow['decision_state']['records'].values():
            rec['latest_proposal']=copy.deepcopy(rec['proposal']);rec['latest_proposal']['facts']['spend']*=2
            rec['decision_due_at']=now.isoformat()
        if d.render_campaign_messages(tomorrow):raise RuntimeError('Unconfirmed next-day repeat')
        confirmed=copy.deepcopy(tomorrow)
        for rec in confirmed['decision_state']['records'].values():d.owner_decision(confirmed['decision_state'],rec['id'],True,now+timedelta(days=1),authorized=True)
        if len(d.render_campaign_messages(confirmed))!=1:raise RuntimeError('Confirmed reminder regression')
        before_other={k:v for k,v in baseline['payload'].get('records',{}).items() if k not in EXPECTED}
        after_other={k:v for k,v in final.get('records',{}).items() if k not in EXPECTED}
        proof.update(complete=True,status='confirmed',canonical_state_readback_verified=True,receipt_readback_verified=True,
            unrelated_records_unchanged=before_other==after_other,stage='proposed_not_owner_confirmed',
            unconfirmed_next_day_messages=0,confirmed_reminder_verified_on_copy=True)
except Exception as exc:
    proof.update(status='incomplete',error_type=type(exc).__name__,error=str(exc)[:250])
finally:
    requests.sessions.Session.request=native
    seal('approved-short-content-delivery',proof)
    print(json.dumps({k:proof.get(k) for k in ('status','complete','telegram_calls','decoded_bytes','error_type','wb_writes','source_calls')}))
if not proof['complete']:raise SystemExit(1)
