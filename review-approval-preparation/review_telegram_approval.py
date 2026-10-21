"""Disabled-by-default, isolated Telegram review approval preparation.

No WB/Telegram clients or old queue imports. Repository transactions serialize
decisions for one review; publisher gets only immutable new approval intents.
"""
import contextlib,hashlib,hmac,json,re,secrets,time
def sha(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def identity(cabinet,kind,item_id):
    if cabinet not in ('token_1','token_2','token_3') or kind not in ('feedbacks','questions') or not str(item_id):raise ValueError('Invalid review identity')
    return json.dumps([cabinet,kind,str(item_id)],separators=(',',':'))
class Rejected(ValueError):pass
class Repository:
    def __init__(self,connection,postgres=False):
        self.conn=connection;self.pg=postgres;self.prefix='review_approval.' if postgres else ''
        if postgres:self.conn.autocommit=True
    def execute(self,sql,args=()):
        return self.conn.execute(sql.replace('{p}',self.prefix).replace('?', '%s') if self.pg else sql.replace('{p}',''),args)
    def setup(self):
        if self.pg:self.conn.execute('CREATE SCHEMA IF NOT EXISTS review_approval')
        for table in ('items','cards','events','intents'):
            self.execute('CREATE TABLE IF NOT EXISTS {p}'+table+' (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        self.conn.commit()
    @contextlib.contextmanager
    def transaction(self):
        if self.pg:
            with self.conn.transaction():yield
        else:
            self.conn.execute('BEGIN IMMEDIATE')
            try:yield;self.conn.commit()
            except BaseException:self.conn.rollback();raise
    def get(self,table,key,lock=False):
        if table not in ('items','cards','events','intents'):raise ValueError('Table')
        tail=' FOR UPDATE' if lock and self.pg else ''
        row=self.execute('SELECT payload FROM {p}'+table+' WHERE id=?'+tail,(key,)).fetchone()
        return json.loads(row[0]) if row else None
    def put(self,table,key,value):
        if table not in ('items','cards','events','intents'):raise ValueError('Table')
        self.execute('INSERT INTO {p}'+table+'(id,payload) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(key,json.dumps(value,ensure_ascii=False,sort_keys=True)))
    def count(self,table):
        if table not in ('items','cards','events','intents'):raise ValueError('Table')
        return self.execute('SELECT count(*) FROM {p}'+table).fetchone()[0]
class Approval:
    def __init__(self,repo,secret,owner_id,chat_id,bot_id,enabled=False,clock=time.time):
        if not secret or not all(str(x) for x in (owner_id,chat_id,bot_id)):raise ValueError('Explicit authentication configuration required')
        self.repo=repo;self.secret=secret;self.owner=str(owner_id);self.chat=str(chat_id);self.bot=str(bot_id);self.enabled=enabled;self.clock=clock;self.legacy_chat=self.chat;self.group={};self.group_actor=None
        if repo.pg:
            row=repo.conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key=%s",('reviews:content-group:v1',)).fetchone()
            self.group=row[0] if row else {}
    def group_chat(self):
        return str(self.group.get("chat_id","")) if self.group.get("enabled") is True and self.group.get("destination_verified") is True else ""
    def allowed_chat_type(self,kind):
        return kind in ("group","supergroup") if self.chat==self.group_chat() else kind=="private"
    def actor_allowed(self,actor):
        return str(actor)==self.owner if self.chat!=self.group_chat() else str(actor)==str(self.group_actor)
    def card_chat(self,card):
        return str(card.get("chat_id",self.legacy_chat))
    def delivery_chat(self):
        destination=self.group_chat()
        if destination:return destination
        if self.repo.pg:raise Rejected('Verified content-group delivery is required')
        return self.chat
    def create(self,cabinet,kind,item_id,version,source,texts,message_id,ttl=None,binding=None,order_status=None):
        ref=identity(cabinet,kind,item_id)
        if len(texts) not in (1,2) or not all(isinstance(t,str) and t.strip() for t in texts) or (len(texts)==2 and texts[0]==texts[1]):raise ValueError('One revised text or two distinct variants required')
        if not version or not all(k in source for k in ('buyer','rating','text','pros','cons','article')):raise ValueError('Original context required')
        if not isinstance(message_id,int) or message_id<=0:raise ValueError('Bind a confirmed Telegram message id')
        token=secrets.token_hex(16)
        with self.repo.transaction():
            # Create row first so Postgres has a concrete key to lock even for concurrent first cards.
            self.repo.execute('INSERT INTO {p}items(id,payload) VALUES (?,?) ON CONFLICT(id) DO NOTHING',(ref,json.dumps({'status':'open'})))
            item=self.repo.get('items',ref,lock=True)
            if item.get('status') in ('held','approved','publishing','uncertain','sent'):raise Rejected('Review held, answered or publication unresolved')
            old=self.repo.get('cards',item.get('token','')) if item.get('token') else None
            if old and old.get('version')==version:
                if old['hashes']!=[sha(t) for t in texts] or old['source']!=source:raise Rejected('Same version content changed')
                raise Rejected('Version already has a card; use its delivery journal, do not resend')
            card={'ref':ref,'cabinet':cabinet,'kind':kind,'item_id':str(item_id),'version':version,'source':source,'texts':texts,'hashes':[sha(t) for t in texts],'message_id':message_id,'expires_at':None if ttl is None else self.clock()+ttl,'status':'awaiting','selected':None,'nonce':None}
            card['chat_id']=self.chat
            card['order_status']=order_status
            if binding is not None:card['binding']=binding
            self.repo.put('cards',token,card)
            self.repo.put('items',ref,{'status':'open','token':token,'version':version})
        return token,self.view(token)
    def keyboard(self,token,card):
        def button(text,action):
            data='rv1:'+token+':'+action
            if len(data.encode())>64:raise ValueError('Callback too long')
            return {'text':text,'callback_data':data}
        if card['status']=='selected':
            return {'inline_keyboard':[[button('Подтвердить публикацию','ok.'+card['nonce'])],[button('Назад','back'),button('Отложить','hold')]]}
        if card['status'] not in ('awaiting','selected'):return {'inline_keyboard':[]}
        return {'inline_keyboard':([[button('Подтвердить публикацию','p1')]] if len(card['texts'])==1 else [[button('Опубликовать вариант 1','p1')],[button('Опубликовать вариант 2','p2')]])+[[button('Доработать','edit'),button('Отложить','hold')]]}
    def view(self,token,card=None):
        card=card or self.repo.get('cards',token)
        if not card:raise Rejected('Unknown card')
        s=card['source']
        lines=['Кабинет: '+{'token_1':'ООО','token_2':'ИП','token_3':'Китай'}[card['cabinet']],('[Вопросы:согласование]' if card['kind']=='questions' else '[Отзывы:согласование]'),s['article']+' · '+card['version']]
        lines+=['ID '+('вопроса' if card['kind']=='questions' else 'отзыва')+': '+card['item_id'],'Покупатель: '+str(s['buyer'] or 'Имя не указано')]
        if card['kind']=='questions':lines+=['Вопрос: '+str(s['text'] or '(без текста)')]
        else:lines+=['Статус покупки: '+{'buyout':'Выкуп','rejected':'Отказ','returned':'Возврат'}.get(card.get('order_status'),'WB не передал статус'),'Оценка: '+str(s['rating'])+'/5','Отзыв: '+str(s['text'] or '(без текста)'),'Достоинства: '+str(s['pros'] or '(не заполнены)'),'Недостатки: '+str(s['cons'] or '(не заполнены)')]
        if card['status']=='selected':
            lines+=['','Выбран вариант '+str(card['selected']+1)+':',card['texts'][card['selected']],'','Подтвердить именно этот текст? Перед отправкой проверим WB.']
        elif card['status']=='approved':
            lines+=['','Согласование сохранено. Публикация ещё не подтверждена WB.']
            if card.get('publication_enabled') is False:lines+=['Отправка WB сейчас выключена. Повторно подтверждать текст не нужно.']
            if card.get('retry_at',0)>self.clock():
                from datetime import datetime,timezone,timedelta
                stamp=datetime.fromtimestamp(card['retry_at'],timezone(timedelta(hours=3))).strftime('%H:%M:%S')
                lines+=['Пауза WB. Проверку можно продолжить после '+stamp+' МСК. Повторно нажимать не нужно.']
        elif card['status']=='sent':
            lines+=['',('Ответ опубликован для всех.' if card.get('wb_ui_status')=='Опубликован для всех' else 'WB подтвердил приём ответа. Публичная публикация может проходить модерацию.'),'Точное совпадение текста подтверждено чтением WB.']
        elif card['status']=='manual_present':lines+=['','В WB уже есть другой ответ. Повторная публикация остановлена.']
        elif card['status']=='uncertain':lines+=['','Исход публикации пока не подтверждён. Повторная отправка запрещена; требуется чтение WB.']
        elif card['status']=='held':lines+=['','Отложено по решению владельца. Ответ и напоминания заблокированы.']
        elif card['status']=='rework':lines+=['','Нужна доработка. Ответьте на это сообщение и укажите правки; новая версия потребует нового согласования.']
        else:
            for n,text in enumerate(card['texts'],1):lines+=['','Вариант '+str(n)+':',text]
            lines+=['','Кнопка «Опубликовать» подтверждает выбранный текст и ставит его в автоматическую отправку WB.']
        return {'text':'\n'.join(lines),'reply_markup':self.keyboard(token,card),'message_id':card['message_id'],'status':card['status']}
    def handle(self,update,header):
        if not self.enabled:raise Rejected('Review callback integration disabled')
        if not hmac.compare_digest(str(header),self.secret):raise Rejected('Webhook authentication failed')
        q=update.get('callback_query') or {}
        msg=q.get('message') or {}
        if not self.actor_allowed(q.get('from',{}).get('id')) or str(msg.get('chat',{}).get('id'))!=self.chat:raise Rejected('Wrong owner or chat')
        if not self.allowed_chat_type(msg.get('chat',{}).get('type')) or str(msg.get('from',{}).get('id'))!=self.bot or msg.get('forward_origin'):raise Rejected('Wrong message origin')
        data=q.get('data','')
        match=re.fullmatch(r'rv1:([0-9a-f]{32}):(v1|v2|p1|p2|edit|hold|back|ok\.[0-9a-f]{12})',data)
        if not match or len(data.encode())>64 or not isinstance(q.get('id'),str) or not q['id']:raise Rejected('Invalid callback')
        token,action=match.groups()
        with self.repo.transaction():
            if self.repo.pg:self.repo.execute('SELECT pg_advisory_xact_lock(hashtextextended(?,0))',('review-callback:'+q['id'],))
            card=self.repo.get('cards',token)
            if not card:raise Rejected('Unknown card')
            item=self.repo.get('items',card['ref'],lock=True)
            card=self.repo.get('cards',token)
            if self.card_chat(card)!=self.chat or msg.get('message_id')!=card['message_id']:raise Rejected('Wrong message binding')
            if item.get('token')!=token or item.get('version')!=card['version']:raise Rejected('Outdated card')
            if card.get('expires_at') is not None and self.clock()>card['expires_at']:raise Rejected('Expired card')
            if card['hashes']!=[sha(t) for t in card['texts']]:raise Rejected('Text checksum changed')
            old=self.repo.get('events',q['id'])
            fingerprint=sha([token,action,str(q['from']['id']),self.chat,card['message_id']])
            if old:
                if old['fingerprint']!=fingerprint:raise Rejected('Callback id reused with different content')
                return {'duplicate':True,'result':old['result'],'answer_callback_query':{'callback_query_id':q['id'],'text':'Уже обработано'}}
            # A delayed/repeated final click acknowledges the same immutable intent.
            # It never creates another intent or changes the approved answer.
            duplicate_selection=int(action[-1])-1 if action in ('p1','p2') else card.get('selected')
            if (action in ('p1','p2') or action=='ok.'+str(card.get('nonce'))) and duplicate_selection in range(len(card['texts'])):
                existing_id=sha([card['ref'],card['version'],card['hashes'][duplicate_selection]])
                existing=self.repo.get('intents',existing_id)
                if existing and existing.get('card_token')==token and existing.get('answer_sha256')==card['hashes'][duplicate_selection] and existing.get('owner_id')==self.owner and existing.get('chat_id')==self.chat:
                    return {'duplicate':True,'result':{'decision':'approved','intent_id':existing_id,'publication_created':False},'answer_callback_query':{'callback_query_id':q['id'],'text':'Согласование уже сохранено. Повторная отправка не создаётся.'}}
            if item['status'] in ('held','sent','uncertain','publishing'):raise Rejected('Review blocked or already answered')
            if item['status']=='approved':raise Rejected('Approval already recorded; do not enqueue again')
            if action in ('v1','v2'):
                if card['status'] not in ('awaiting','selected'):raise Rejected('Card not selectable')
                selected=int(action[-1])-1
                if selected>=len(card['texts']):raise Rejected('Variant unavailable')
                # A repeated choice must not invalidate the confirmation already displayed.
                if card['status']!='selected' or card['selected']!=selected:
                    card.update(status='selected',selected=selected,nonce=secrets.token_hex(6))
                result={'decision':'selected','variant':card['selected']+1,'publication_created':False}
            elif action=='back':
                if card['status']!='selected':raise Rejected('No selection')
                card.update(status='awaiting',selected=None,nonce=None)
                result={'decision':'back','publication_created':False}
            elif action=='edit':
                if card['status'] not in ('awaiting','selected'):raise Rejected('Cannot revise this card')
                card.update(status='rework',selected=None,nonce=None);item['status']='rework'
                result={'decision':'rework','publication_created':False}
            elif action=='hold':
                card.update(status='held',selected=None,nonce=None);item['status']='held'
                result={'decision':'held','publication_created':False}
            else:
                if action in ('p1','p2'):
                    if card['status'] not in ('awaiting','selected'):raise Rejected('Card not approvable')
                    selected=int(action[-1])-1
                    if selected>=len(card['texts']):raise Rejected('Variant unavailable')
                    card.update(selected=selected,nonce=None)
                else:
                    if card['status']!='selected' or action!='ok.'+str(card['nonce']):raise Rejected('Outdated confirmation')
                    selected=card['selected']
                intent_id=sha([card['ref'],card['version'],card['hashes'][selected]])
                intent={'id':intent_id,'ref':card['ref'],'cabinet':card['cabinet'],'kind':card['kind'],'item_id':card['item_id'],'version':card['version'],'answer':card['texts'][selected],'answer_sha256':card['hashes'][selected],'source_sha256':sha(card['source']),'owner_id':self.owner,'chat_id':self.chat,'callback_id':q['id'],'approved_by_user_id':str(q['from']['id']),'status':'awaiting_preflight','created_at':self.clock(),'card_token':token}
                if self.repo.get('intents',intent_id):raise Rejected('Publication intent exists')
                self.repo.put('intents',intent_id,intent)
                card['status']='approved';item['status']='approved'
                result={'decision':'approved','intent_id':intent_id,'publication_created':True,'wb_write_performed':False}
            self.repo.put('items',card['ref'],item);self.repo.put('cards',token,card)
            self.repo.put('events',q['id'],{'fingerprint':fingerprint,'result':result,'created_at':self.clock(),'owner_id':self.owner,'actor_id':str(q['from']['id'])})
            view=self.view(token,card)
            return {'duplicate':False,'result':result,'edit_message':view,'answer_callback_query':{'callback_query_id':q['id'],'text':{'selected':'Проверьте выбранный текст','approved':'Согласование сохранено; ждём проверку WB','held':'Отложено','rework':'Ожидаю ваши правки','back':'Вернулись к выбору'}[result['decision']]}}
    def set_item_state(self,ref,status,reason):
        # Trusted source/journal bridge, not a Telegram command; never releases a hold implicitly.
        if status not in ('held','sent','uncertain','publishing'):raise ValueError('Unsupported external state')
        with self.repo.transaction():
            self.repo.execute('INSERT INTO {p}items(id,payload) VALUES (?,?) ON CONFLICT(id) DO NOTHING',(ref,json.dumps({'status':'open'})))
            old=self.repo.get('items',ref,lock=True)
            old.update(status=status,reason=reason)
            self.repo.put('items',ref,old)
    def record_edit(self,token,actor,chat,message_id,text):
        if not self.actor_allowed(actor) or str(chat)!=self.chat or not text.strip():raise Rejected('Invalid owner edit')
        with self.repo.transaction():
            card=self.repo.get('cards',token)
            if not card or self.card_chat(card)!=self.chat or card['message_id']!=message_id:raise Rejected('Reply to the exact review message')
            item=self.repo.get('items',card['ref'],lock=True)
            if item.get('token')!=token or item.get('status')!='rework':raise Rejected('No pending rework for this card')
            key='edit:'+sha([token,str(actor),message_id,text])
            if self.repo.get('events',key):return {'status':'revision_requested','old_version_approvable':False,'publication_created':False,'duplicate':True,'revision_event_id':key}
            self.repo.put('events',key,{'decision':'revision_requested','token':token,'version':card['version'],'instruction':text,'actor':str(actor),'chat_id':self.chat,'created_at':self.clock()})
            return {'status':'revision_requested','old_version_approvable':False,'publication_created':False,'revision_event_id':key}



