"""Rebind two authenticated saved rework updates after an exact UI-only move."""
import copy
from review_telegram_approval import sha,Rejected

def rebind_saved_rework(card,token,migration,edit_update,reply_update,chat,bot):
    if migration.get('status')!='confirmed' or migration.get('card_token')!=token:
        raise Rejected('Confirmed migration required')
    old=migration.get('old_message_id');new=migration.get('message_id')
    before=dict(card,message_id=old)
    if (card.get('status')!='awaiting' or card.get('message_id')!=new
        or str(card.get('chat_id'))!=str(chat) or sha(before)!=migration.get('fingerprint')):
        raise Rejected('Card changed after migration')
    q=edit_update.get('callback_query') or {}
    msg=reply_update.get('message') or {};origin=msg.get('reply_to_message') or {}
    callback_message=q.get('message') or {}
    actor=q.get('from') or {}
    if q.get('data')!='rv1:'+token+':edit':raise Rejected('Only saved rework action can be recovered')
    if actor.get('is_bot') or not isinstance(actor.get('id'),int) or actor.get('id')!=(msg.get('from') or {}).get('id'):
        raise Rejected('Authenticated participant mismatch')
    if not isinstance(msg.get('text'),str) or not msg['text'].strip():raise Rejected('Saved text required')
    for value in (callback_message,origin):
        if (value.get('message_id')!=old or str((value.get('chat') or {}).get('id'))!=str(chat)
            or str((value.get('from') or {}).get('id'))!=str(bot)):
            raise Rejected('Saved bot message binding mismatch')
    if str((msg.get('chat') or {}).get('id'))!=str(chat):raise Rejected('Wrong reply chat')
    edit=copy.deepcopy(edit_update);reply=copy.deepcopy(reply_update)
    edit['callback_query']['message']['message_id']=new
    reply['message']['reply_to_message']['message_id']=new
    return edit,reply

