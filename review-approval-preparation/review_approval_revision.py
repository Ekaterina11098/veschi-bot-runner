"""Turn a saved owner reply into a new exact-text approval, never publication."""
import json,time,re

def ready_owner_text(text):
    return len(text.strip())>=60 and bool(re.search(r'с уважением,\s*команда\s+VESCHI',text,re.I))
from review_telegram_approval import sha,Rejected
from review_approval_notice import NewNotice

def revise(approval,bridge,store,telegram,event_id,preserve,cutover):
    repo=approval.repo;event=repo.get('events',event_id)
    if not event or event.get('decision')!='revision_requested' or event.get('actor')!=approval.owner:raise Rejected('Owner revision unavailable')
    old=repo.get('cards',event['token']);ref=repo.get('items',old['ref']) if old else None
    delivery_key='revision-delivery:'+sha(event_id)
    previous=repo.get('events',delivery_key)
    if previous and previous.get('status')!='needs_full_text':return previous
    if not old or not ref or ref.get('status')!='rework' or ref.get('token')!=event['token']:raise Rejected('Revision is no longer current')
    binding=old.get('binding') or {};draft=bridge.source.read(binding.get('draft_key',''))
    if not draft or draft.get('source_sha256')!=binding.get('raw_source_sha256'):raise Rejected('Original source unavailable')
    sources=bridge.source.matching(old['cabinet'],old['kind'],old['item_id'],'reviews:source:')
    originals=[s for s in sources if s.get('version')==old['version']]
    if len(originals)!=1 or sha(originals[0]['item'])!=draft['source_sha256']:raise Rejected('Original review source mismatch')
    item=originals[0]['item'];answer=event['instruction'].strip()
    from validator import validate_answer
    check=dict(item)
    if old['kind']=='questions':check['productValuation']=0
    validation=validate_answer(answer,check)
    if not ready_owner_text(answer):
        if previous:return previous
        # A short instruction is preserved, not mistaken for a ready answer.
        result={'status':'needs_full_text','revision_event_id':event_id}
        with repo.transaction():repo.put('events',delivery_key,dict(result,delivery='sending'))
        preserve()
        response=telegram.call('sendMessage',{'chat_id':approval.chat,'text':'Правки получены и сохранены. Пришлите готовый текст ответа целиком ответом на прежнюю карточку — верну его для подтверждения. В WB ничего не отправлено.'})
        result.update(message_id=response['message_id'])
        with repo.transaction():repo.put('events',delivery_key,result)
        preserve();return result
    version=old['version']+'-edit-'+sha(event_id)[:8]
    stamp=time.time();cabinet=old['cabinet'];kind=old['kind'];item_id=old['item_id']
    store.insert('reviews:source:'+sha([cabinet,kind,item_id,version]),dict(cabinet=cabinet,kind=kind,item_id=item_id,version=version,item=item,source_sha256=sha(item),observed_at=stamp))
    store.insert(bridge.draft_key(cabinet,kind,item_id,version),dict(schema_version=1,cabinet=cabinet,kind=kind,item_id=item_id,version=version,source_sha256=sha(item),variants=[answer],confirmation_status='draft',approved_variant=None,owner_supplied=True,ai_style_validation=validation))
    preserve()
    result=NewNotice(approval,bridge,telegram,enabled=True,preserve=preserve).deliver(item,cabinet,kind,version,stamp,cutover)
    result=dict(result,revision_event_id=event_id)
    with repo.transaction():repo.put('events',delivery_key,result)
    preserve();return result

