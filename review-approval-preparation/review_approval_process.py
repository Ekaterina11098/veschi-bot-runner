"""Dedicated event entry, disabled unless both deployment flags are explicitly set."""
import base64,json,os
from pathlib import Path
from review_telegram_approval import Approval,Repository,Rejected,sha
from review_approval_bridge import SQLSource,DurableBridge
from review_telegram_runtime import TelegramTransport,CanonicalGuard
from review_telegram_receiver import Receiver
from review_approval_executor import Executor,WBAdapter
from review_approval_backup import snapshot,encrypt

def decrypt_update(raw,key):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    envelope=json.loads(raw)
    if envelope.get('format')!='review-approval-update-v1':raise ValueError('Ingress format')
    data=AESGCM(base64.b64decode(key,validate=True)).decrypt(base64.b64decode(envelope['nonce'],validate=True),base64.b64decode(envelope['ciphertext'],validate=True),b'review-approval-update-v1')
    if len(data)>65536:raise ValueError('Ingress size')
    return json.loads(data)

def process(approval,bridge,telegram,wb,update,publication_enabled=False,preserve=None,new_notices_enabled=False,cutover=None):
    guard=CanonicalGuard(approval,bridge.project)
    if update.get('new_notice'):
        from review_approval_notice import NewNotice
        data=update['new_notice']
        if str(data.get('owner_id'))!=approval.owner or str(data.get('chat_id'))!=approval.chat or cutover is None:raise Rejected('Invalid new notice authorization/cutover')
        return NewNotice(approval,bridge,telegram,enabled=new_notices_enabled,preserve=preserve).deliver(data['item'],data['cabinet'],data['kind'],data['version'],data['observed_at'],cutover)
    if update.get('resume_intent'):
        intent=approval.repo.get('intents',update['resume_intent'])
        if not intent or str(update.get('owner_id'))!=approval.owner or str(update.get('chat_id'))!=approval.chat or intent['owner_id']!=approval.owner or intent['chat_id']!=approval.chat:raise Rejected('Invalid targeted continuation')
        result={'result':{'decision':'approved','intent_id':intent['id']},'targeted_resume':True}
    else:result=Receiver(approval,telegram,guard,preserve=preserve).receive(update,approval.secret)
    # Persist encrypted supplement BEFORE a possible publication.
    if preserve:preserve()
    if result.get('status')=='revision_requested' and new_notices_enabled:
        from review_approval_revision import revise
        from review_durable_workflow import DurableReviews
        from review_queue import _request
        from review_approval_notice import NewNoticeTransport
        result['revision_delivery']=revise(approval,bridge,DurableReviews(_request),NewNoticeTransport(os.environ['TELEGRAM_BOT_TOKEN']),result['revision_event_id'],preserve,cutover)
    decision=result.get('result',{})
    if decision.get('decision')=='approved':
        from review_approval_card_delivery import dismiss_approved
        token=approval.repo.get('intents',decision['intent_id'])['card_token']
        removal=dismiss_approved(approval,telegram,token,preserve)
        result['card_removal']=removal['status']
    if decision.get('decision')=='approved' and publication_enabled:
        outcome=Executor(approval,guard,wb,enabled=True,preserve=preserve).run(decision['intent_id'])
        result['publication_status']=outcome['status']
        card_token=approval.repo.get('intents',decision['intent_id'])['card_token']
        with approval.repo.transaction():
            card=approval.repo.get('cards',card_token,lock=True)
            card['status']={'confirmed':'sent','manual_present':'manual_present','verify':'uncertain','blocked':'held'}.get(outcome['status'],'approved')
            card['publication_enabled']=True
            card['retry_at']=outcome.get('retry_at',0)
            approval.repo.put('cards',card_token,card)
        from review_approval_card_delivery import notify_owner_problem
        problem=notify_owner_problem(approval,telegram,outcome,preserve)
        if problem:result['owner_problem_delivery']=problem['status']
    elif decision.get('decision')=='approved':
        token=approval.repo.get('intents',decision['intent_id'])['card_token']
        with approval.repo.transaction():
            card=approval.repo.get('cards',token,lock=True);card['publication_enabled']=False
            approval.repo.put('cards',token,card)
    if decision.get('decision')=='approved':
        from review_approval_card_delivery import notify_owner_receipt
        saved=approval.repo.get('intents',decision['intent_id'])
        result['owner_receipt_delivery']=notify_owner_receipt(approval,telegram,saved,preserve)['status']
    if preserve:preserve()
    return result

def main():
    if os.getenv('REVIEW_APPROVAL_ENABLED')!='1':raise Rejected('Review approval disabled')
    import psycopg
    import wildberries
    conn=psycopg.connect(os.environ['REVIEW_APPROVAL_DSN'],autocommit=True,connect_timeout=10,options='-c statement_timeout=30000')
    try:
        # GitHub pending concurrency drops older callbacks. Keep every run and
        # serialize its complete decision + Telegram edit on this DB session.
        conn.execute("SELECT pg_advisory_lock(hashtextextended('review-approval-process-ui-v1',0))")
        approval=Approval(Repository(conn,postgres=True),os.environ['REVIEW_APPROVAL_INGRESS_KEY'],os.environ['REVIEW_APPROVAL_OWNER_ID'],os.environ['TELEGRAM_ALLOWED_CHAT_ID'],os.environ['REVIEW_APPROVAL_BOT_ID'],enabled=True)
        bridge=DurableBridge(approval,SQLSource(conn))
        output=Path(os.environ['RUNNER_TEMP'])/'review-approval-output';output.mkdir(exist_ok=True)
        def preserve():
            sealed=encrypt(snapshot(approval.repo),os.environ['RECOVERY_PUBLIC_KEY'].encode())
            target=output/'approval-supplement.aes.json';target.write_text(json.dumps(sealed))
        update=decrypt_update(os.environ['SEALED_UPDATE'],os.environ['REVIEW_APPROVAL_INGRESS_KEY'])
        ingress_key='telegram-ingress:'+sha(update)
        with approval.repo.transaction():
            previous=approval.repo.get('events',ingress_key)
            if not previous:approval.repo.put('events',ingress_key,{'status':'received','update':update})
        preserve()
        try:
            from review_approval_notice import NewNoticeTransport
            transport=NewNoticeTransport if update.get('new_notice') else TelegramTransport
            result=process(approval,bridge,transport(os.environ['TELEGRAM_BOT_TOKEN']),WBAdapter(wildberries),update,publication_enabled=os.getenv('REVIEW_PUBLICATION_ENABLED')=='1',preserve=preserve,new_notices_enabled=os.getenv('REVIEW_NEW_NOTICES_ENABLED')=='1',cutover=float(os.environ['REVIEW_APPROVAL_CUTOVER']) if os.getenv('REVIEW_APPROVAL_CUTOVER') else None)
            with approval.repo.transaction():approval.repo.put('events',ingress_key,{'status':'processed','update':update,'result':result})
            # Categories only, no answer/source/identity or credential in public log.
            print(json.dumps({'decision':result.get('result',{}).get('decision'),'publication_status':result.get('publication_status'),'ui_delivery':result.get('ui_delivery')}))
        except Exception as exc:
            with approval.repo.transaction():approval.repo.put('events',ingress_key,{'status':'failed','update':update,'error_type':type(exc).__name__,'error':str(exc)[:300]})
            raise
        finally:preserve()
    finally:conn.close()

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'error_type':type(exc).__name__,'completed':False}))
        raise SystemExit(1)
