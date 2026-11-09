"""Delete tracked completed approval messages, including exact authenticated owner replies."""
import json
from review_telegram_approval import sha
NORMAL=frozenset(('approved','verifying','accepted','public'))
def cleanup_completed(a,tg,preserve=None,intent_id=None,cabinet=None):
    # Worker starts in the legacy private chat; sweep the verified group too.
    original=a.chat
    report={'deleted':0,'already_deleted':0,'unconfirmed':0}
    try:
        for chat in dict.fromkeys(filter(None,(original,a.group_chat()))):
            a.chat=chat
            for key,value in _cleanup_chat(a,tg,preserve,intent_id,cabinet).items():report[key]+=value
    finally:a.chat=original
    return report

def _cleanup_chat(a,tg,preserve=None,intent_id=None,cabinet=None):
    repo=a.repo
    if repo.pg:
        intents={k:json.loads(v) for k,v in repo.execute("SELECT id,payload FROM {p}intents WHERE payload::jsonb->>'owner_id'=? AND payload::jsonb->>'chat_id'=? AND (?::text IS NULL OR id=?) AND (?::text IS NULL OR payload::jsonb->>'cabinet'=?)",(a.owner,a.chat,intent_id,intent_id,cabinet,cabinet)).fetchall()}
        refs=list({i['ref'] for i in intents.values()})
        cards={k:json.loads(v) for k,v in repo.execute("SELECT id,payload FROM {p}cards WHERE payload::jsonb->>'ref'=ANY(?)",(refs,)).fetchall()} if refs else {}
        # Keep old card versions and exact revision/reply lineage, not unrelated
        # events from every review. Terminal deletion receipts remain point reads.
        events={k:json.loads(v) for k,v in repo.execute("SELECT id,payload FROM {p}events WHERE payload::jsonb->>'intent_id'=ANY(?) OR payload::jsonb->>'card_token'=ANY(?) OR payload::jsonb->>'ref'=ANY(?) OR (starts_with(id,'telegram-ingress:') AND payload::jsonb->'update'->'message'->'reply_to_message'->>'message_id'=ANY(?)) OR (starts_with(id,'revision-delivery:') AND payload::jsonb->>'revision_event_id' IN (SELECT id FROM {p}events WHERE starts_with(id,'edit:') AND payload::jsonb->>'token'=ANY(?))) OR (starts_with(id,'edit:') AND payload::jsonb->>'token'=ANY(?))",(list(intents),list(cards),refs,[str(c['message_id']) for c in cards.values() if c.get('message_id')],list(cards),list(cards))).fetchall()} if intents else {}
    else:
        intents={k:json.loads(v) for k,v in repo.execute('SELECT id,payload FROM {p}intents').fetchall()}
        cards={k:json.loads(v) for k,v in repo.execute('SELECT id,payload FROM {p}cards').fetchall()}
        events={k:json.loads(v) for k,v in repo.execute('SELECT id,payload FROM {p}events').fetchall()}
    owned={}
    completed={}
    processed={}
    skip=set()
    for key,i in intents.items():
        if cabinet and i.get('cabinet')!=cabinet:continue
        if intent_id and key!=intent_id:continue
        card=cards.get(i.get('card_token'));item=repo.get('items',i.get('ref',''))
        if card and card.get('delivery_mode')=='automatic_policy':continue
        if not card or i.get('owner_id')!=a.owner or i.get('chat_id')!=a.chat:continue
        if i.get('answer_sha256')!=sha(i.get('answer')) or i.get('answer_sha256') not in card.get('hashes',[]):continue
        if any(i.get(k)!=card.get(k) for k in ('ref','cabinet','kind','item_id','version')):continue
        owned[key]=i
        if item and item.get('token')==i['card_token'] and item.get('status') in ('approved','sent'):
            processed[i['ref']]=i
        if i.get('status')=='confirmed' and i.get('actual_answer_sha256')==i['answer_sha256'] and item and item.get('token')==i['card_token'] and item.get('status')=='sent':
            completed[i['ref']]=i
    tokens={k for k,c in cards.items() if c.get('ref') in processed and a.card_chat(c)==a.chat}
    targets=set()
    def add(value):
        if isinstance(value,int) and not isinstance(value,bool) and value>0:targets.add(value)
    for token in tokens:
        card=cards[token];removal=card.get('telegram_card_removal') or {}
        if removal.get('status')=='confirmed':skip.add(card['message_id'])
        else:add(card.get('message_id'))
    for key,e in events.items():
        if key.startswith(('owner-receipt:','owner-problem:')) and str(e.get('chat_id',a.legacy_chat))!=a.chat:continue
        if key.startswith('owner-receipt:') and e.get('intent_id') in owned and e.get('stage') in NORMAL:add(e.get('message_id'))
        elif e.get('card_token') in tokens:add(e.get('message_id'))
        elif e.get('ref') in processed and key.startswith('new-notice:'):add(e.get('message_id'))
        elif key.startswith(('owner-receipt:','owner-problem:')) and e.get('intent_id') in owned and owned[e['intent_id']]['ref'] in completed:add(e.get('message_id'))
        elif key.startswith('revision-delivery:'):
            edit=events.get(e.get('revision_event_id'),{})
            if edit.get('token') in tokens:add(e.get('message_id'))
    # Owner explicitly requested removing their completed reply messages too.
    # Match authenticated owner replies in private or the verified content group to a tracked card AND the exact approved text.
    by_message={c.get('message_id'):(token,c) for token,c in cards.items() if a.card_chat(c)==a.chat}
    # A history move keeps the old bot message as a durable UI alias.
    # Recover exact replies to that message without broadening text/actor checks.
    aliases=[]
    for alias_key,alias in events.items():
        if not alias_key.startswith('resurface-old:') or str(alias.get('chat_id'))!=a.chat:continue
        alias_token=alias.get('card_token');alias_card=cards.get(alias_token)
        mid=alias.get('message_id')
        if alias_token not in tokens or not alias_card or a.card_chat(alias_card)!=a.chat:continue
        if not isinstance(mid,int) or isinstance(mid,bool) or mid<=0:continue
        if mid in by_message and by_message[mid][0]!=alias_token:continue
        by_message[mid]=(alias_token,alias_card);aliases.append(str(mid))
    if repo.pg and aliases:
        extra=repo.execute("SELECT id,payload FROM {p}events WHERE starts_with(id,'telegram-ingress:') AND payload::jsonb->'update'->'message'->'chat'->>'id'=? AND payload::jsonb->'update'->'message'->'reply_to_message'->>'message_id'=ANY(?)",(a.chat,aliases)).fetchall()
        events.update({k:json.loads(v) for k,v in extra})
    for key,e in events.items():
        if not key.startswith('telegram-ingress:'):continue
        message=(e.get('update') or {}).get('message') or {}
        actor=str((message.get('from') or {}).get('id'))
        chat=message.get('chat') or {}
        if str(chat.get('id'))!=a.chat or not a.allowed_chat_type(chat.get('type')):continue
        reply=message.get('reply_to_message') or {}
        if str((reply.get('from') or {}).get('id'))!=a.bot:continue
        original=by_message.get(reply.get('message_id'))
        if not original:continue
        token,original=original
        # Group permissions are checked when record_edit accepts the reply.
        # The durable authenticated edit receipt binds actor, chat, card and text;
        # workers do not carry the ingress handler's transient group_actor.
        if actor!=a.owner:
            if a.chat!=a.group_chat():continue
            if not any(k.startswith('edit:') and edit.get('token')==token
                       and str(edit.get('actor'))==actor
                       and str(edit.get('chat_id'))==a.chat
                       and edit.get('decision')=='revision_requested'
                       and edit.get('instruction')==message.get('text','').strip()
                       for k,edit in events.items()):continue
        intent=processed.get(original.get('ref'))
        if intent and isinstance(message.get('text'),str) and message['text'].strip()==intent['answer']:
            add(message.get('message_id'))
    targets-=skip
    report={'deleted':0,'already_deleted':0,'unconfirmed':0}
    dirty=False
    if targets and preserve:preserve()
    for mid in sorted(targets):
        key='telegram-cleanup:'+a.chat+':'+str(mid)
        with repo.transaction():
            if repo.pg:repo.execute('SELECT pg_advisory_xact_lock(hashtextextended(?,0))',(key,))
            old=repo.get('events',key,lock=True) or {}
            if old.get('status')=='confirmed':
                report['already_deleted']+=1;continue
            if old.get('retry_at',0)>a.clock() or old.get('attempts',0)>=3:continue
            event=dict(status='deleting',message_id=mid,chat_id=a.chat,attempts=old.get('attempts',0)+1,retry_at=a.clock()+300)
            repo.put('events',key,event)
        try:
            response=tg.call('deleteMessage',{'chat_id':a.chat,'message_id':mid})
            if response is not True and not (isinstance(response,dict) and response.get('ok') is True):raise RuntimeError('Deletion unconfirmed')
            event.update(status='confirmed',checked_at=a.clock());report['deleted']+=1
        except Exception:
            event.update(status='uncertain',checked_at=a.clock());report['unconfirmed']+=1
        with repo.transaction():repo.put('events',key,event)
        dirty=True
    if dirty and preserve:preserve()
    return report


