"""One explicitly renewed owner attempt. Exact646 only; all I/O journaled.

The previous uncertain attempt remains in history. This authorization permits
ONE new POST after fresh absence; no rejection/timeout automatically rearms it.
"""
import copy,time,hashlib,os
from urllib.parse import urlsplit
from review_telegram_approval import sha,Rejected

INTENT='04e4512dd295c953dce3707c2a5049d79c985bbffc16379515bd44df662a6028'
CARD='359dfd9c3eee92d596247c388dd9b6f4'
ANSWER='9b224203e606ce4c6a132f2d782f86b20e24e8830e329883bf948829f5005e5d'
VERSION='owner-telegram-first-20261015-1792066028'
ITEM='FCFR5A3pNgvsDFnWShPZ'
AUTH='owner-controlled-retry:646:20261016:v1'
# Exact646 owner previously allowed <=900sec after proven429. Prior scoped
# receipts prove649/654sec burst waits; no global rate-limit change is made.
FRESH_SECONDS=900
BURST_GAP=660
HEADERS=('x-ratelimit-retry','x-ratelimit-reset','x-ratelimit-limit','x-ratelimit-remaining','retry-after')

class Retry:
    def __init__(self,approval,wb,guard,preserve=lambda:None,clock=time.time):
        self.a=approval;self.repo=approval.repo;self.wb=wb;self.guard=guard
        self.preserve=preserve;self.clock=clock;self.http_buffer=[];self.allow_post=False
    def binding(self):
        i=self.repo.get('intents',INTENT);c=self.repo.get('cards',CARD)
        if not i or not c or i['id']!=INTENT or c.get('message_id')!=646:
            raise Rejected('Exact646 identity unavailable')
        if any(i.get(k)!=v or c.get(k)!=v for k,v in
               (('cabinet','token_1'),('kind','feedbacks'),('item_id',ITEM),('version',VERSION))):
            raise Rejected('Exact646 scope mismatch')
        if i.get('card_token')!=CARD or i.get('answer_sha256')!=ANSWER or sha(i['answer'])!=ANSWER or c['hashes'][0]!=ANSWER:
            raise Rejected('Immutable646 text mismatch')
        if i.get('owner_id')!=self.a.owner or i.get('chat_id')!=self.a.chat or i.get('ref')!=c.get('ref'):
            raise Rejected('Owner646 binding mismatch')
        if i.get('source_sha256')!=sha(c.get('source')) or sha(c['texts'][0])!=ANSWER:
            raise Rejected('Original646 source/text changed')
        return i,c
    def operation(self):return self.repo.get('events',AUTH)
    def save(self,op,**fields):
        op.update(fields,updated_at=self.clock())
        with self.repo.transaction():
            current=self.repo.get('events',AUTH,lock=True)
            if current:
                # HTTP observer commits while a caller holds an older operation
                # object. Never let that object erase newly recorded requests.
                logs=copy.deepcopy(current.get('http_log') or [])
                identities={(r.get('request_id'),r.get('phase')) for r in logs}
                for row in op.get('http_log') or []:
                    key=(row.get('request_id'),row.get('phase'))
                    if key not in identities:logs.append(copy.deepcopy(row));identities.add(key)
                op['http_log']=logs
                op['post_consumed']=bool(op.get('post_consumed') or current.get('post_consumed'))
                op['http_post_started']=bool(op.get('http_post_started') or current.get('http_post_started'))
            self.repo.put('events',AUTH,op)
        if self.repo.get('events',AUTH)!=op:raise RuntimeError('Retry journal readback mismatch')
        self.preserve()
        return op
    def initialize(self):
        i,c=self.binding();op=self.operation()
        if op:return op
        op=dict(id=AUTH,authorization_source='owner_chat_20261016_one_controlled_repeat',
            owner_ui_absence_sha256='b4bb827a1328f64d70485c6225ce7b650ca9161e8ae0b0178f33cf663f08fc3e',
            intent_id=INTENT,answer_sha256=ANSWER,created_at=self.clock(),
            original_unknown_attempt=copy.deepcopy(i),status='preflight',post_consumed=False,
            http_post_started=False,http_log=[],freshness_seconds=FRESH_SECONDS,
            prior_explicit_429_evidence=dict(run_id=38811374262,retry_seconds=649),
            rate_gap_seconds=BURST_GAP)
        return self.save(op)
    def record(self,record):
        self.http_buffer.append(copy.deepcopy(record))
        op=self.operation();op['http_log'].append(copy.deepcopy(record))
        # Buffer is also sealed independently if the DB fails after an HTTP call.
        self.preserve()
        return self.save(op)
    def install_http_journal(self,requests,dbhost):
        native=requests.sessions.Session.request
        def observed(session,method,url,*args,**kwargs):
            method=method.upper();u=urlsplit(str(url))
            if u.hostname==dbhost:return native(session,method,url,*args,**kwargs)
            exact_get=(method=='GET' and u.hostname=='feedbacks-api.wildberries.ru'
                and u.path=='/api/v1/feedback' and (kwargs.get('params') or {}).get('id')==ITEM)
            exact_post=(method=='POST' and u.hostname=='feedbacks-api.wildberries.ru'
                and u.path=='/api/v1/feedbacks/answer' and (kwargs.get('json') or {}).get('id')==ITEM
                and sha((kwargs.get('json') or {}).get('text'))==ANSWER)
            if not(exact_get or exact_post):raise Rejected('Request outside exact646 recovery')
            self.binding();op=self.operation()
            if exact_post:
                if not self.allow_post or not op.get('post_consumed') or op.get('http_post_started'):
                    raise Rejected('One POST budget unavailable')
                self.save(op,http_post_started=True,http_post_started_at=self.clock())
                self.allow_post=False
            request_id=str(len(op['http_log']))+':'+str(self.clock())
            base=dict(request_id=request_id,method=method,path=u.path,started_at=self.clock())
            self.record(dict(base,phase='before_http',outcome='pending'))
            try:response=native(session,method,url,*args,**kwargs)
            except Exception as exc:
                self.record(dict(base,phase='after_http',outcome='transport_unknown',error_type=type(exc).__name__))
                raise
            body=None
            try:body=response.json()
            except Exception:pass
            rec=dict(base,phase='after_http',finished_at=self.clock(),http_status=int(response.status_code),
                headers={str(k).lower():str(v)[:80] for k,v in response.headers.items() if str(k).lower() in HEADERS},
                response_body_sha256=hashlib.sha256(response.content).hexdigest(),
                application_error=isinstance(body,dict) and body.get('error') is True,
                outcome='http_accepted' if 200<=response.status_code<300 else 'http_rejected')
            # No response text, authorization, tokens or cookies in the log.
            if isinstance(body,dict):
                rec['error_field_types']={k:type(body[k]).__name__ for k in ('error','errorText','title','detail','code','status') if k in body}
                secrets=[v for k,v in os.environ.items() if k.startswith('WB_') and v]
                rec['response_error']={}
                for key in ('error','errorText','title','detail','code','status'):
                    if isinstance(body.get(key),(str,int,float,bool)):
                        value=str(body[key])[:1500]
                        for secret in secrets:value=value.replace(secret,'[REDACTED]')
                        rec['response_error'][key]=value
            self.record(rec)
            return response
        requests.sessions.Session.request=observed
        return lambda:setattr(requests.sessions.Session,'request',native)
    def complete(self,actual,status):
        i,c=self.binding();op=self.operation()
        with self.repo.transaction():
            i['status']=status;i['actual_answer_sha256']=sha(actual);i['actual_answer']=actual
            i['controlled_retry_authorization']=AUTH;i['confirmed_at']=self.clock()
            self.repo.put('intents',INTENT,i)
            item=self.repo.get('items',i['ref']);item['status']='sent';self.repo.put('items',i['ref'],item)
            c['status']='sent' if status=='confirmed' else 'manual_present';self.repo.put('cards',CARD,c)
        if self.repo.get('intents',INTENT)!=i:raise RuntimeError('Final646 intent readback mismatch')
        return self.save(op,status=status,actual_answer_sha256=sha(actual),readback_at=self.clock())
    def verify_rejection(self):
        """Read the result of the consumed attempt; NEVER rearm a POST."""
        i,c=self.binding();op=self.operation()
        if not op or op['status']!='rejected' or not op.get('post_consumed'):
            raise Rejected('No consumed rejected attempt')
        if op.get('rejection_checked_at'):return op
        pause=max(0,self.wb.pause('token_1'))
        if pause:return dict(op,wait_seconds=pause)
        try:actual=self.wb.read(i)
        except Exception as exc:
            pause=max(0,self.wb.pause('token_1'))
            self.save(op,rejection_read_error_type=type(exc).__name__)
            return dict(op,wait_seconds=pause) if pause else self.save(op,rejection_read_needs_diagnosis=True)
        if not isinstance(actual,str):return self.save(op,rejection_read_needs_diagnosis=True)
        if actual:return self.complete(actual,'confirmed' if actual==i['answer'] else 'manual_present')
        return self.save(op,rejection_checked_at=self.clock(),rejection_readback_empty=True,
            rejection_readback_sha256=sha(actual),no_further_post_authorized=True)
    def step(self):
        i,c=self.binding();op=self.initialize();now=self.clock()
        if i['status'] in ('confirmed','manual_present'):
            return self.save(op,status=i['status'],actual_answer_sha256=i.get('actual_answer_sha256'))
        if op['status'] in ('confirmed','manual_present','rejected','needs_diagnosis','blocked'):return op
        pause=max(0,self.wb.pause('token_1'))
        wait=max(pause,op.get('not_before',0)-now)
        if wait>0:return dict(op,wait_seconds=wait)
        if op.get('post_consumed'):
            # A consumed or uncertain attempt can ONLY be read back.
            try:actual=self.wb.read(i)
            except Exception as exc:
                return self.save(op,status='verify',last_read_error_type=type(exc).__name__,
                    not_before=now+max(self.wb.pause('token_1'),BURST_GAP))
            if not isinstance(actual,str):return self.save(op,status='needs_diagnosis',reason='Unknown readback shape')
            if actual:return self.complete(actual,'confirmed' if actual==i['answer'] else 'manual_present')
            return self.save(op,status='verify',last_readback_empty_at=self.clock(),not_before=self.clock()+BURST_GAP)
        fresh=(isinstance(op.get('preflight_at'),(int,float)) and 0<=now-op['preflight_at']<=FRESH_SECONDS)
        if not fresh:
            try:actual=self.wb.read(i)
            except Exception as exc:
                if self.wb.pause('token_1')>0:
                    return self.save(op,status='preflight',not_before=now+self.wb.pause('token_1'),last_read_error_type=type(exc).__name__)
                return self.save(op,status='needs_diagnosis',last_read_error_type=type(exc).__name__)
            if not isinstance(actual,str):return self.save(op,status='needs_diagnosis',reason='Unknown preflight shape')
            if actual:return self.complete(actual,'confirmed' if actual==i['answer'] else 'manual_present')
            return self.save(op,status='preflight_verified',preflight_at=self.clock(),preflight_answer_absent=True,
                not_before=self.clock()+BURST_GAP)
        if not self.guard(c):return self.save(op,status='blocked',reason='Canonical hold/version/state changed')
        # Commit consumption BEFORE calling POST. Crash/restart never rearms it.
        self.save(op,status='write_intent',post_consumed=True,write_intent_at=self.clock())
        self.allow_post=True;exception=None
        try:self.wb.post(i)
        except Exception as exc:exception=type(exc).__name__
        finally:self.allow_post=False
        op=self.operation()
        responses=[r for r in op['http_log'] if r['method']=='POST' and r['phase']=='after_http']
        response=responses[-1] if responses else {}
        code=response.get('http_status')
        fields=dict(post_http_status=code,post_exception_type=exception,post_response=response,
            not_before=self.clock()+max(BURST_GAP,self.wb.pause('token_1')))
        if isinstance(code,int) and (not 200<=code<300 or response.get('application_error')):
            return self.save(op,status='rejected',**fields)
        with self.repo.transaction():
            current=self.repo.get('intents',INTENT)
            current['controlled_retry_authorization']=AUTH;current['controlled_retry_http_status']=code
            current['controlled_retry_http_accepted']=isinstance(code,int) and 200<=code<300
            self.repo.put('intents',INTENT,current)
        return self.save(op,status='verify',**fields)