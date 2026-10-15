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
        self.repo=repo;self.secret=secret;self.owner=str(owner_id);self.chat=str(chat_id);self.bot=str(bot_id);self.enabled=enabled;self.clock=clock
    def create(self,cabinet,kind,item_id,version,source,texts,message_id,ttl=86400,binding=None):
        ref=identity(cabinet,kind,item_id)
        if len(texts)!=2 or not all(isinstance(t,str) and t.strip() for t in texts) or texts[0]==texts[1]:raise ValueError('Two distinct texts required')
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
            card={'ref':ref,'cabinet':cabinet,'kind':kind,'item_id':str(item_id),'version':version,'source':source,'texts':texts,'hashes':[sha(t) for t in texts],'message_id':message_id,'expires_at':self.clock()+ttl,'status':'awaiting','selected':None,'nonce':None}
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
        return {'inline_keyboard':[[button('Вариант 1','v1'),button('Вариант 2','v2')],[button('Доработать','edit'),button('Отложить','hold')]]}
    def view(self,token,card=None):
        card=card or self.repo.get('cards',token)
        if not card:raise Rejected('Unknown card')
        s=card['source']
        lines=['[Отзывы:согласование]',{'token_1':'ООО','token_2':'ИП','token_3':'Китай'}[card['cabinet']]+' · '+s['article']+' · '+card['version']]
        lines+=['Покупатель: '+str(s['buyer'] or 'не указано'),'Оценка: '+str(s['rating'])+'/5','Отзыв: '+str(s['text'] or '(без текста)'),'Достоинства: '+str(s['pros'] or '(не заполнены)'),'Недостатки: '+str(s['cons'] or '(не заполнены)')]
        if card['status']=='selected':
            lines+=['','Выбран вариант '+str(card['selected']+1)+':',card['texts'][card['selected']],'','Подтвердить именно этот текст? Перед отправкой проверим WB.']
        elif card['status']=='approved':lines+=['','Согласование сохранено. Публикация ещё не подтверждена WB.']
        elif card['status']=='sent':lines+=['','Ответ опубликован. Точное совпадение текста подтверждено чтением WB.']
        elif card['status']=='manual_present':lines+=['','В WB уже есть другой ответ. Повторная публикация остановлена.']
        elif card['status']=='uncertain':lines+=['','Исход публикации пока не подтверждён. Повторная отправка запрещена; требуется чтение WB.']
        elif card['status']=='held':lines+=['','Отложено по решению владельца. Ответ и напоминания заблокированы.']
        elif card['status']=='rework':lines+=['','Нужна доработка. Ответьте на это сообщение и укажите правки; новая версия потребует нового согласования.']
        else:
            for n,text in enumerate(card['texts'],1):lines+=['','Вариант '+str(n)+':',text]
        return {'text':'\n'.join(lines),'reply_markup':self.keyboard(token,card),'message_id':card['message_id'],'status':card['status']}
    def handle(self,update,header):
        if not self.enabled:raise Rejected('Review callback integration disabled')
        if not hmac.compare_digest(str(header),self.secret):raise Rejected('Webhook authentication failed')
        q=update.get('callback_query') or {}
        msg=q.get('message') or {}
        if str(q.get('from',{}).get('id'))!=self.owner or str(msg.get('chat',{}).get('id'))!=self.chat:raise Rejected('Wrong owner or chat')
        if msg.get('chat',{}).get('type')!='private' or str(msg.get('from',{}).get('id'))!=self.bot or msg.get('forward_origin'):raise Rejected('Wrong message origin')
        data=q.get('data','')
        match=re.fullmatch(r'rv1:([0-9a-f]{32}):(v1|v2|edit|hold|back|ok\.[0-9a-f]{12})',data)
        if not match or len(data.encode())>64 or not isinstance(q.get('id'),str) or not q['id']:raise Rejected('Invalid callback')
        token,action=match.groups()
        with self.repo.transaction():
            if self.repo.pg:self.repo.execute('SELECT pg_advisory_xact_lock(hashtextextended(?,0))',('review-callback:'+q['id'],))
            card=self.repo.get('cards',token)
            if not card:raise Rejected('Unknown card')
            item=self.repo.get('items',card['ref'],lock=True)
            card=self.repo.get('cards',token)
            if msg.get('message_id')!=card['message_id']:raise Rejected('Wrong message binding')
            if item.get('token')!=token or item.get('version')!=card['version']:raise Rejected('Outdated card')
            if self.clock()>card['expires_at']:raise Rejected('Expired card')
            if card['hashes']!=[sha(t) for t in card['texts']]:raise Rejected('Text checksum changed')
            old=self.repo.get('events',q['id'])
            fingerprint=sha([token,action,self.owner,self.chat,card['message_id']])
            if old:
                if old['fingerprint']!=fingerprint:raise Rejected('Callback id reused with different content')
                return {'duplicate':True,'result':old['result'],'answer_callback_query':{'callback_query_id':q['id'],'text':'Уже обработано'}}
            if item['status'] in ('held','sent','uncertain','publishing'):raise Rejected('Review blocked or already answered')
            if item['status']=='approved':raise Rejected('Approval already recorded; do not enqueue again')
            if action in ('v1','v2'):
                if card['status'] not in ('awaiting','selected'):raise Rejected('Card not selectable')
                card.update(status='selected',selected=int(action[-1])-1,nonce=secrets.token_hex(6))
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
                if card['status']!='selected' or action!='ok.'+str(card['nonce']):raise Rejected('Outdated confirmation')
                selected=card['selected']
                intent_id=sha([card['ref'],card['version'],card['hashes'][selected]])
                intent={'id':intent_id,'ref':card['ref'],'cabinet':card['cabinet'],'kind':card['kind'],'item_id':card['item_id'],'version':card['version'],'answer':card['texts'][selected],'answer_sha256':card['hashes'][selected],'source_sha256':sha(card['source']),'owner_id':self.owner,'chat_id':self.chat,'callback_id':q['id'],'status':'awaiting_preflight','created_at':self.clock(),'card_token':token}
                if self.repo.get('intents',intent_id):raise Rejected('Publication intent exists')
                self.repo.put('intents',intent_id,intent)
                card['status']='approved';item['status']='approved'
                result={'decision':'approved','intent_id':intent_id,'publication_created':True,'wb_write_performed':False}
            self.repo.put('items',card['ref'],item);self.repo.put('cards',token,card)
            self.repo.put('events',q['id'],{'fingerprint':fingerprint,'result':result,'created_at':self.clock(),'owner_id':self.owner})
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
        if str(actor)!=self.owner or str(chat)!=self.chat or not text.strip():raise Rejected('Invalid owner edit')
        with self.repo.transaction():
            card=self.repo.get('cards',token)
            if not card or card['message_id']!=message_id:raise Rejected('Reply to the exact review message')
            item=self.repo.get('items',card['ref'],lock=True)
            if item.get('token')!=token or item.get('status')!='rework':raise Rejected('No pending rework for this card')
            key='edit:'+sha([token,str(actor),message_id,text])
            if self.repo.get('events',key):return {'status':'revision_requested','old_version_approvable':False,'publication_created':False,'duplicate':True}
            self.repo.put('events',key,{'decision':'revision_requested','token':token,'version':card['version'],'instruction':text,'actor':self.owner,'created_at':self.clock()})
            return {'status':'revision_requested','old_version_approvable':False,'publication_created':False}

