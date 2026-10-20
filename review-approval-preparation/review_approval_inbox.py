"""Replay only authenticated encrypted review updates, independent of dispatch success.

The webhook appends ciphertext to a service-only cache. The decision/event journal
is authoritative; a crash after approval can never create another publication.
Caller holds the existing review UI session lock, including read/modify delivery.
"""
from review_telegram_approval import Rejected,sha

PREFIX='reviews:telegram-ingress:v1:'
TERMINAL=('processed','rejected')

def process_update(approval,bridge,telegram,update,preserve=None,**options):
    from review_approval_process import process
    key='telegram-ingress:'+sha(update)
    previous=approval.repo.get('events',key)
    if previous and previous.get('status') in TERMINAL:
        return dict(previous.get('result') or {},already_processed=True)
    with approval.repo.transaction():
        approval.repo.put('events',key,dict(status='received',update=update,received_at=approval.clock()))
    # Never wait for WB while accepting/serializing Telegram decisions.
    result=process(approval,bridge,telegram,None,update,publication_enabled=False,preserve=preserve,**options)
    if result.get('ui_delivery')=='uncertain':
        with approval.repo.transaction():
            approval.repo.put('events',key,dict(status='ui_pending',update=update,result=result,checked_at=approval.clock()))
        raise RuntimeError('Saved Telegram decision needs UI repair')
    with approval.repo.transaction():
        approval.repo.put('events',key,dict(status='processed',update=update,result=result,processed_at=approval.clock()))
    return result

def pending(repo,now,limit=25):
    return repo.conn.execute("""SELECT c.cache_key,c.payload FROM review_approval.source_cache c
        LEFT JOIN review_approval.events e ON e.id='telegram-inbox:'||c.cache_key
        WHERE starts_with(c.cache_key,%s)
          AND coalesce(e.payload::jsonb->>'status','') NOT IN ('processed','rejected')
        ORDER BY (c.payload->>'update_id')::bigint,c.cache_key LIMIT %s""",(PREFIX,limit)).fetchall()

def drain(approval,bridge,telegram,key,preserve=None,limit=25,**options):
    from review_approval_process import decrypt_update
    repo=approval.repo;report={'processed':0,'rejected':0,'retry':0};blocked=set()
    for cache_key,payload in pending(repo,approval.clock(),limit):
        receipt='telegram-inbox:'+cache_key
        previous=repo.get('events',receipt) or {}
        attempts=previous.get('attempts',0)+1
        route=None
        try:
            update=decrypt_update(payload['sealed_update'],key)
            if update.get('update_id')!=payload.get('update_id') or not isinstance(update.get('update_id'),int):
                raise Rejected('Inbox update identity mismatch')
            # Edge inbox accepts only real Telegram messages/callbacks, never internal commands.
            if update.get('new_notice') or update.get('resume_intent') or not (update.get('callback_query') or update.get('message')):
                raise Rejected('Inbox update outside Telegram scope')
            q=update.get('callback_query') or {};message=q.get('message') or update.get('message') or {}
            route=(str(message.get('chat',{}).get('id')),str(message.get('message_id') if q else (message.get('reply_to_message') or {}).get('message_id')))
            if route in blocked:continue
            if previous.get('retry_at',0)>approval.clock():
                blocked.add(route);continue
            result=process_update(approval,bridge,telegram,update,preserve=preserve,**options)
            status='processed';extra={'decision':result.get('result',{}).get('decision')}
        except Exception as exc:
            # A temporary canonical read error fails closed, but must not lose the click.
            transient=not isinstance(exc,(Rejected,ValueError,KeyError,TypeError)) or str(exc)=='Canonical state temporarily unavailable'
            status='retry' if transient else 'rejected'
            extra={'error_type':type(exc).__name__,'error':str(exc)[:300]}
            if status=='retry':
                extra.update(retry_at=approval.clock()+min(300,5*2**min(attempts,6)),requires_attention=attempts>=6)
                blocked.add(route)
        with repo.transaction():
            repo.put('events',receipt,dict(status=status,attempts=attempts,checked_at=approval.clock(),**extra))
        report[status]+=1
        if preserve:preserve()
        # Preserve order for the same card; a broken card cannot stop other cabinets.
    return report
