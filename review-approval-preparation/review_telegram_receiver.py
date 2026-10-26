"""Dedicated callback receiver. No legacy dispatcher, polling, schedules or WB client.

Transport is injected; production deployment and webhook registration are separate.
Only edits/acknowledgements to an existing, bound review message are permitted.
"""
import hmac
import json
from review_telegram_approval import Rejected


class Receiver:
    def __init__(self, approval, telegram, reconcile, preserve=None):
        self.approval = approval
        self.telegram = telegram
        self.preserve = preserve
        # Must read canonical draft version, holds, publication journal and WB/manual state.
        # Return False if incomplete/unavailable. No mutation of WB is allowed here.
        self.reconcile = reconcile

    def receive(self, update, header):
        a = self.approval
        if not a.enabled:
            raise Rejected('Review callback integration disabled')
        if not hmac.compare_digest(str(header), a.secret):
            raise Rejected('Webhook authentication failed')
        q = update.get('callback_query')
        inbound=(q or {}).get('message') or update.get('message') or {}
        actor=(q or {}).get('from') or inbound.get('from') or {}
        chat=inbound.get('chat') or {}
        a.group_actor=None
        if str(chat.get('id'))==a.group_chat():
            if actor.get('is_bot') or not isinstance(actor.get('id'),int) or chat.get('type') not in ('group','supergroup'):
                raise Rejected('Invalid group actor')
            member=self.telegram.call('getChatMember',{'chat_id':a.group_chat(),'user_id':actor['id']})
            if member.get('user',{}).get('id')!=actor['id'] or member.get('status') not in ('creator','administrator','member'):
                raise Rejected('Group membership required')
            a.chat=a.group_chat();a.group_actor=str(actor['id'])
        else:
            a.chat=a.legacy_chat
        if q:
            # Authenticate before any source read. Core repeats full validation.
            msg = q.get('message') or {}
            if not a.actor_allowed(q.get('from', {}).get('id')) or str(msg.get('chat', {}).get('id')) != a.chat:
                raise Rejected('Wrong owner or chat')
            data = str(q.get('data', ''))
            if not data.startswith('rv1:'):
                return {'ignored': True}
            token = data.split(':')[1]
            card = a.repo.get('cards', token)
            if not card:
                raise Rejected('Unknown card')
            if a.card_chat(card)!=a.chat or msg.get('message_id') != card['message_id'] or not a.allowed_chat_type(msg.get('chat',{}).get('type')) or str(msg.get('from',{}).get('id'))!=a.bot or msg.get('forward_origin'):
                raise Rejected('Wrong message binding')
            if not self.reconcile(card):
                try:self.telegram.call('answerCallbackQuery',{'callback_query_id':q.get('id',''),'text':'Согласование остановлено: данные изменились, ответ уже есть или действует блокировка.','show_alert':True})
                except Exception:pass
                raise Rejected('Canonical state temporarily unavailable' if getattr(self.reconcile,'last_reason',None)=='unavailable' else 'Canonical review state unavailable or blocked')
            try:result = a.handle(update, header)
            except Rejected:
                try:self.telegram.call('answerCallbackQuery',{'callback_query_id':q.get('id',''),'text':'Эта кнопка устарела или действие уже завершено. Используйте актуальную версию.','show_alert':True})
                except Exception:pass
                raise
            # A delivery failure cannot roll back a decision. Duplicate callback never
            # re-enqueues publication; render current state, not an old selection.
            view = a.view(token)
            try:
                if a.repo.get('cards',token)['status']=='approved':
                    from review_approval_card_delivery import dismiss_approved
                    removal=dismiss_approved(a,self.telegram,token,self.preserve)
                    if removal['status']!='confirmed':raise RuntimeError('Card removal unconfirmed')
                else:
                    self.telegram.call('editMessageText', {
                        'chat_id': a.chat, 'message_id': view['message_id'],
                        'text': view['text'], 'reply_markup': view['reply_markup'],
                    })
            except Exception:
                return dict(result, ui_delivery='uncertain', automatic_retry=False)
            try:
                self.telegram.call('answerCallbackQuery', result['answer_callback_query'])
                ack='confirmed'
            except Exception:ack='unconfirmed'
            return dict(result, ui_delivery='confirmed', callback_ack=ack)
        msg = update.get('message') or {}
        # Ordinary commands are deliberately ignored, never added to telegram_jobs.
        reply = msg.get('reply_to_message') or {}
        if not reply or not msg.get('text'):
            return {'ignored': True}
        if not a.actor_allowed(msg.get('from', {}).get('id')) or str(msg.get('chat', {}).get('id')) != a.chat:
            raise Rejected('Wrong owner or chat')
        if not a.allowed_chat_type(msg.get('chat', {}).get('type')) or str(reply.get('from', {}).get('id')) != a.bot:
            raise Rejected('Wrong reply origin')
        rows = a.repo.execute('SELECT id,payload FROM {p}cards').fetchall()
        matches = [(token, json.loads(payload)) for token, payload in rows
                   if a.card_chat(json.loads(payload))==a.chat and json.loads(payload)['message_id'] == reply.get('message_id')]
        if len(matches) != 1:
            raise Rejected('Unknown or ambiguous review message')
        token, card = matches[0]
        original_token, original_message_id = token, reply['message_id']
        item = a.repo.get('items',card['ref']) or {}
        if item.get('token') and item['token'] != token:
            # A real reply to an older bound card may edit only the current
            # pending rework of the same unchanged source. Never forward clicks.
            current_token = item['token']
            current = a.repo.get('cards',current_token)
            if (not current or item.get('status') != 'rework'
                or current.get('status') != 'rework'
                or a.card_chat(current) != a.chat
                or any(current.get(k) != card.get(k) for k in ('ref','cabinet','kind','item_id','source'))
                or any(json.loads(row[0]).get('ref') == card['ref']
                       for row in a.repo.execute('SELECT payload FROM {p}intents').fetchall())):
                raise Rejected('Old reply cannot replace the current decision')
            token, card = current_token, current
        if not self.reconcile(card):
            raise Rejected('Canonical state temporarily unavailable' if getattr(self.reconcile,'last_reason',None)=='unavailable' else 'Canonical review state unavailable or blocked')
        result = a.record_edit(token, str(msg['from']['id']), a.chat, card['message_id'], msg['text'])
        if token != original_token:
            with a.repo.transaction():
                a.repo.put('events','reply-route:'+str(msg.get('message_id'))+':'+token,
                    dict(original_token=original_token,original_message_id=original_message_id,
                         current_token=token,revision_event_id=result['revision_event_id'],
                         actor=str(msg['from']['id']),chat_id=a.chat))
        return result

    def wsgi(self, environ, start_response):
        if environ.get('REQUEST_METHOD') != 'POST':
            start_response('405 Method Not Allowed', []); return [b'']
        try:
            size = int(environ.get('CONTENT_LENGTH') or 0)
            if not 0 < size <= 65536:
                raise ValueError('Body size')
            update = json.loads(environ['wsgi.input'].read(size))
            self.receive(update, environ.get('HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN', ''))
            status = '200 OK'
        except Rejected:
            # Invalid/stale clicks cannot become a retry loop or publication.
            status = '200 OK'
        except (ValueError, TypeError, AttributeError):
            status = '400 Bad Request'
        except Exception:
            status = '503 Service Unavailable'
        start_response(status, [('Content-Type', 'text/plain')])
        return [b'OK']


