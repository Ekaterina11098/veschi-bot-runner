"""Execute one new Telegram approval intent only. No legacy queue enumeration."""
from review_telegram_approval import Rejected,sha

class ExplicitRateLimit(Exception):
    def __init__(self,seconds):self.seconds=max(1,int(seconds))

class WBAdapter:
    def __init__(self,module):self.wb=module
    def pause(self,cabinet):return self.wb.review_pause_seconds(cabinet=cabinet)
    def read(self,intent):
        try:return self.wb.get_reply_answer(intent['item_id'],intent['kind'],cabinet=intent['cabinet'])
        except self.wb.ReviewRateLimit as exc:raise ExplicitRateLimit(exc.retry_seconds) from None
    def post(self,intent):
        function=self.wb.post_question_reply if intent['kind']=='questions' else self.wb.post_review_reply
        try:function(intent['item_id'],intent['answer'],cabinet=intent['cabinet'])
        except self.wb.ReviewRateLimit as exc:raise ExplicitRateLimit(exc.retry_seconds) from None

class Executor:
    def __init__(self,approval,guard,wb,enabled=False,preserve=None):
        self.a=approval;self.repo=approval.repo;self.guard=guard;self.wb=wb;self.enabled=enabled;self.preserve=preserve
    def run(self,intent_id):
        if not self.enabled:raise Rejected('Publication disabled')
        if self.repo.pg:
            acquired=self.repo.execute('SELECT pg_try_advisory_lock(hashtextextended(?,0))',('review-approval:'+intent_id,)).fetchone()[0]
            if not acquired:return {'busy':True}
            try:return self._leased_run(intent_id)
            finally:self.repo.execute('SELECT pg_advisory_unlock(hashtextextended(?,0))',('review-approval:'+intent_id,))
        return self._leased_run(intent_id)
    def _leased_run(self,intent_id):
        # Serialize the whole specific operation. A crash releases this row lock,
        # but the committed verify state prevents a second WB write.
        intent=self.repo.get('intents',intent_id)
        if not intent:raise Rejected('Unknown new approval intent')
        with self.repo.transaction():
            self.repo.get('items',intent['ref'],lock=True)
            intent=self.repo.get('intents',intent_id,lock=True)
            if intent['status'] in ('confirmed','manual_present','blocked'):return intent
            if intent.get('lease_until',0)>self.a.clock():return dict(intent,busy=True)
            intent['lease_until']=self.a.clock()+120
            self.repo.put('intents',intent_id,intent)
        try:return self._run(intent)
        finally:
            with self.repo.transaction():
                current=self.repo.get('intents',intent_id,lock=True)
                current['lease_until']=0;self.repo.put('intents',intent_id,current)
    def save(self,intent,status,**extra):
        with self.repo.transaction():
            item=self.repo.get('items',intent['ref'],lock=True)
            intent.update(status=status,**extra);self.repo.put('intents',intent['id'],intent)
            item['status']='sent' if status in ('confirmed','manual_present') else ('uncertain' if status=='verify' else item['status'])
            self.repo.put('items',intent['ref'],item)
        if self.repo.get('intents',intent['id'])!=intent:raise RuntimeError('Intent readback mismatch')
        if self.preserve:self.preserve()
        return intent
    def _run(self,intent):
        card=self.repo.get('cards',intent['card_token'])
        if not card or any(intent[key]!=card[key] for key in ('ref','cabinet','kind','item_id','version')) or sha(intent['answer'])!=intent['answer_sha256'] or intent['answer_sha256'] not in card['hashes'] or intent['source_sha256']!=sha(card['source']):raise Rejected('Immutable answer binding failed')
        # Verification is read-only even if a hold appeared after sending.
        if intent['status']=='verify':return self.verify(intent)
        if intent.get('retry_at',0)>self.a.clock():return intent
        if self.wb.pause(intent['cabinet']):return intent
        if not self.guard(card):return self.save(intent,'blocked',reason='Canonical hold/version/journal')
        verified_at=intent.get('preflight_verified_at')
        fresh=(isinstance(verified_at,(int,float)) and 0<=self.a.clock()-verified_at<=900)
        if not fresh:
            try:actual=self.wb.read(intent)
            except ExplicitRateLimit as exc:return self.save(intent,intent['status'],retry_at=self.a.clock()+exc.seconds)
            if not isinstance(actual,str):raise Rejected('Unknown WB answer')
            if actual.strip():return self.save(intent,'confirmed' if actual==intent['answer'] else 'manual_present',actual_answer_sha256=sha(actual))
            self.save(intent,intent['status'],preflight_verified_at=self.a.clock())
        # GET can establish a new server pause. Re-read it before saving write intent.
        pause=self.wb.pause(intent['cabinet'])
        if pause:return self.save(intent,intent['status'],retry_at=self.a.clock()+pause)
        if not self.guard(card):return self.save(intent,'blocked',reason='Canonical changed after preflight')
        self.save(intent,'verify',write_intent_at=self.a.clock())
        try:self.wb.post(intent)
        except ExplicitRateLimit as exc:
            return self.save(intent,'awaiting_preflight',last_explicit_rejection='HTTP429',retry_at=self.a.clock()+exc.seconds)
        except Exception:
            # Unknown outcome: commit verify and do not write again.
            return intent
        return self.verify(intent)
    def verify(self,intent):
        if self.wb.pause(intent['cabinet']):return intent
        try:actual=self.wb.read(intent)
        except Exception:return intent
        if not isinstance(actual,str):return intent
        if actual==intent['answer']:return self.save(intent,'confirmed',actual_answer_sha256=sha(actual),confirmed_at=self.a.clock())
        if actual.strip():return self.save(intent,'manual_present',actual_answer_sha256=sha(actual))
        return intent
