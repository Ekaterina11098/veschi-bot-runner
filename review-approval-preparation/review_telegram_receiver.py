"""Dedicated callback receiver. No legacy dispatcher, polling, schedules or WB client.

Transport is injected; production deployment and webhook registration are separate.
Only edits/acknowledgements to an existing, bound review message are permitted.
"""
import hmac
import json
from review_telegram_approval import Rejected


class Receiver:
    def __init__(self, approval, telegram, reconcile):
        self.approval = approval
        self.telegram = telegram
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
        if q:
            # Authenticate before any source read. Core repeats full validation.
            msg = q.get('message') or {}
            if str(q.get('from', {}).get('id')) != a.owner or str(msg.get('chat', {}).get('id')) != a.chat:
                raise Rejected('Wrong owner or chat')
            data = str(q.get('data', ''))
            if not data.startswith('rv1:'):
                return {'ignored': True}
            token = data.split(':')[1]
            card = a.repo.get('cards', token)
            if not card:
                raise Rejected('Unknown card')
            if not self.reconcile(card):
                raise Rejected('Canonical review state unavailable or blocked')
            result = a.handle(update, header)
            # A delivery failure cannot roll back a decision. Duplicate callback never
            # re-enqueues publication; render current state, not an old selection.
            view = a.view(token)
            try:
                self.telegram.call('editMessageText', {
                    'chat_id': a.chat, 'message_id': view['message_id'],
                    'text': view['text'], 'reply_markup': view['reply_markup'],
                })
                self.telegram.call('answerCallbackQuery', result['answer_callback_query'])
                return dict(result, ui_delivery='confirmed')
            except Exception:
                return dict(result, ui_delivery='uncertain', automatic_retry=False)
        msg = update.get('message') or {}
        # Ordinary commands are deliberately ignored, never added to telegram_jobs.
        reply = msg.get('reply_to_message') or {}
        if not reply or not msg.get('text'):
            return {'ignored': True}
        if str(msg.get('from', {}).get('id')) != a.owner or str(msg.get('chat', {}).get('id')) != a.chat:
            raise Rejected('Wrong owner or chat')
        if msg.get('chat', {}).get('type') != 'private' or str(reply.get('from', {}).get('id')) != a.bot:
            raise Rejected('Wrong reply origin')
        rows = a.repo.execute('SELECT id,payload FROM {p}cards').fetchall()
        matches = [(token, json.loads(payload)) for token, payload in rows
                   if json.loads(payload)['message_id'] == reply.get('message_id')]
        if len(matches) != 1:
            raise Rejected('Unknown or ambiguous review message')
        token, card = matches[0]
        if not self.reconcile(card):
            raise Rejected('Canonical review state unavailable or blocked')
        return a.record_edit(token, a.owner, a.chat, reply['message_id'], msg['text'])

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
