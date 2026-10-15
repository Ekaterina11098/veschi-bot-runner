"""Production transport/bootstrap building blocks; no startup or enable side effect."""
import json
import urllib.request
from review_telegram_approval import identity, sha


class TelegramTransport:
    ALLOWED = frozenset(('editMessageText', 'answerCallbackQuery', 'deleteMessage', 'notifyOwnerReviewProblem'))

    def __init__(self, token, opener=urllib.request.urlopen):
        if not token: raise ValueError('Bot token required')
        self._token = token
        self._open = opener

    def call(self, method, payload):
        if method not in self.ALLOWED: raise ValueError('Method outside review approval scope')
        if method=='notifyOwnerReviewProblem':method='sendMessage'
        # Plain text, no parse_mode: source text cannot introduce Telegram markup.
        if method == 'editMessageText' and len(payload['text'].encode('utf-16-le')) // 2 > 4096:
            raise ValueError('Review card too long; split before delivery, never truncate approval text')
        request = urllib.request.Request('https://api.telegram.org/bot'+self._token+'/'+method,
            data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'},method='POST')
        # No HTTP retries here; caller records uncertain UI delivery separately.
        try:
            with self._open(request, timeout=8) as response:
                result=json.load(response)
        except Exception:
            raise RuntimeError('Telegram transport unconfirmed') from None
        if not result.get('ok'): raise RuntimeError('Telegram request rejected')
        return result['result']


class CanonicalGuard:
    """Read adapter contract, fail closed. Never converts absent data to allowed.

    reader(card) must return a consistent current projection from existing durable
    drafts/hold/publication journal. It is intentionally not the old work queue.
    """
    def __init__(self, approval, reader): self.approval=approval; self.reader=reader

    def __call__(self, card):
        try: state=self.reader(card)
        except Exception: return False
        if not isinstance(state,dict) or state.get('complete') is not True: return False
        if state.get('ref')!=card['ref']: return False
        reason=None
        if state.get('hold') is True: reason='held'
        elif state.get('answered') is True: reason='sent'
        elif state.get('publication_state') in ('uncertain','publishing'): reason=state['publication_state']
        if reason:
            self.approval.set_item_state(card['ref'],reason,'canonical reconciliation')
            return False
        return (state.get('hold') is False and state.get('answered') is False
            and state.get('publication_state')=='idle' and state.get('version')==card['version']
            and state.get('hashes')==card['hashes'] and state.get('source_sha256')==sha(card['source']))
