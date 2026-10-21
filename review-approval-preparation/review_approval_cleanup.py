"""Delete tracked completed approval messages, including exact authenticated owner replies."""
import json
from review_telegram_approval import sha
NORMAL=frozenset(('approved','verifying','accepted','public'))
def cleanup_completed(a,tg,preserve=None,intent_id=None):
    repo=a.repo
    intents={k:json.loads(v) for k,v in repo.execute('SELECT id,payload FROM {p}intents').fetchall()}
    cards={k:json.loads(v) for k,v in repo.execute('SELECT id,payload FROM {p}cards').fetchall()}
    events={k:json.loads(v) for k,v in repo.execute('SELECT id,payload FROM {p}events').fetchall()}
    owned={}
    completed={}
    processed={}
    skip=set()
    for key,i in intents.items():
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
        if key.startswith('owner-receipt:') and e.get('intent_id') in owned and e.get('stage') in NORMAL:add(e.get('message_id'))
        elif e.get('card_token') in tokens:add(e.get('message_id'))
        elif e.get('ref') in processed and key.startswith('new-notice:'):add(e.get('message_id'))
        elif key.startswith(('owner-receipt:','owner-problem:')) and e.get('intent_id') in owned and owned[e['intent_id']]['ref'] in completed:add(e.get('message_id'))
        elif key.startswith('revision-delivery:'):
            edit=events.get(e.get('revision_event_id'),{})
            if edit.get('token') in tokens:add(e.get('message_id'))
    # Owner explicitly requested removing their completed reply messages too.
    # Match authenticated private replies to a tracked card AND the exact approved text.
    by_message={c.get('message_id'):c for c in cards.values() if a.card_chat(c)==a.chat}
    for key,e in events.items():
        if not key.startswith('telegram-ingress:'):continue
        message=(e.get('update') or {}).get('message') or {}
        if str((message.get('from') or {}).get('id'))!=a.owner:continue
        chat=message.get('chat') or {}
        if str(chat.get('id'))!=a.chat or chat.get('type')!='private':continue
        reply=message.get('reply_to_message') or {}
        if str((reply.get('from') or {}).get('id'))!=a.bot:continue
        original=by_message.get(reply.get('message_id'))
        if not original:continue
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

