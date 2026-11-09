"""Owner-authorized one-time resurfacing; preserve canonical decisions and exact text."""
from review_telegram_approval import sha

def resurface(a,tg,token,batch):
    repo=a.repo
    key='history-resurface:'+batch+':'+token
    initial=repo.get('cards',token)
    if not initial:return {'status':'skipped'}
    def valid(card,item):
        if not card or not item or item.get('token')!=token:return False
        if a.card_chat(card)!=a.group_chat() or not a.group_chat():return False
        return (card.get('status'),item.get('status')) in (
            ('awaiting','open'),('selected','open'),('rework','rework'))
    def has_intent(ref):
        return any(__import__('json').loads(row[0]).get('ref')==ref
                   for row in repo.execute('SELECT payload FROM {p}intents').fetchall())
    with repo.transaction():
        item=repo.get('items',initial['ref'],lock=True)
        card=repo.get('cards',token,lock=True)
        old=repo.get('events',key,lock=True)
        if old:return old  # Includes submitting/uncertain: never repeat unknown sends.
        if not valid(card,item) or has_intent(card['ref']):return {'status':'skipped'}
        fingerprint=sha(card)
        event=dict(status='submitting',card_token=token,old_message_id=card['message_id'],
                   chat_id=a.group_chat(),created_at=a.clock(),fingerprint=fingerprint)
        repo.put('events',key,event)
    # Durable claim precedes Telegram. Lock canonical state through send and binding.
    with repo.transaction():
        item=repo.get('items',initial['ref'],lock=True)
        card=repo.get('cards',token,lock=True)
        if not valid(card,item) or sha(card)!=fingerprint or has_intent(card['ref']):
            event['status']='skipped_changed';repo.put('events',key,event);return event
        view=a.view(token,card)
        try:
            response=tg.call('sendMessage',dict(chat_id=a.group_chat(),text=view['text'],reply_markup=view['reply_markup']))
            mid=response.get('message_id') if isinstance(response,dict) else None
            if (not isinstance(mid,int) or isinstance(mid,bool) or mid<=0
                or str(response.get('chat',{}).get('id'))!=a.group_chat()):
                raise ValueError('Unconfirmed Telegram result')
        except Exception:
            event.update(status='uncertain',checked_at=a.clock())
            repo.put('events',key,event)
            return event
        # Only UI binding changes. Source, versions, hashes, holds and intents stay exact.
        card['message_id']=mid
        repo.put('cards',token,card)
        repo.put('events','resurface-old:'+batch+':'+token,
                 dict(card_token=token,message_id=event['old_message_id'],chat_id=a.group_chat()))
        event.update(status='confirmed',message_id=mid,checked_at=a.clock())
        repo.put('events',key,event)
    return event

