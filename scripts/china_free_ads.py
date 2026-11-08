"""Reply-bound advertising requests using deterministic collectors, never a model."""
import json,re

def confirmation_text(job):
    text=job.get('request_text','')
    m=next((x for x in job.get('tool_trace',[]) if x.get('name')=='china_saved_question'),{})
    original=m.get('bridge_request_text')
    if (m.get('codex_bridge') is True and m.get('bot_id')==8780468043
        and job.get('chat_id')==-1004342917488 and isinstance(original,str)
        and text=='/codex '+original):
        return original
    return text

def requested_ids(w,job,text):
    catalog=[(int(n),a) for n,a in w.catalog()]
    article_tokens=re.findall(r'(?<![\w-])\d+-[A-Za-z][A-Za-z0-9_-]*',text)
    if any(sum(a.casefold()==token.casefold() for _,a in catalog)!=1 for token in article_tokens):
        raise ValueError('Один из артикулов не найден однозначно. Укажите полные артикулы конкретных вариантов.')
    selected={n for n,a in catalog if a.casefold() in text.casefold() or re.search(r'(?<!\d)'+str(n)+r'(?!\d)',text)}
    if selected:return sorted(selected)
    if re.search(r'(?:артикул\w*|вариант\w*|позици\w*)\s*[:№]?\s*\d|(?:добавь|запусти)\s+\d',text,re.I):
        raise ValueError('Укажите полные артикулы или nmID: короткие номера не должны расширять подбор на другие товары.')
    if not re.search(r'на\s+них|эти\w*\s+(?:товар|вариант|позиц|кандидат)|по\s+ним',text,re.I):return []
    marker=next((x for x in job.get('tool_trace',[]) if x.get('name')=='china_saved_question'),{})
    mid=marker.get('reply_message_id')
    if type(mid) is not int:raise ValueError('Нужно ответить на сообщение со списком конкретных товаров.')
    rows=w.db('GET','telegram_api_cache',params={
        'cache_key':'like.china_agent:codex_bridge:v1:outbox:*',
        'payload->>status':'eq.delivered','payload->>chat_id':'eq.-1004342917488',
        'payload->message_ids':'cs.'+json.dumps([mid]),'select':'payload','limit':2}) or []
    if len(rows)!=1:raise ValueError('Не найден однозначный доставленный список товаров; ответьте на сам список.')
    source=rows[0]['payload']['answer']
    labels=dict(re.findall(r'(?m)^\|\s*(\d+)\s*[—–-]\s*([^|]+)',source))
    priority=re.search(r'Первая очередь[^:\n]*:\s*([\d,\sи]+)',source,re.I)
    codes=set(re.findall(r'\d+',priority[1])) if priority and not re.search(r'\bвсе\b',text,re.I) else set(labels)
    selected={n for n,a in catalog if a.casefold() in source.casefold() and (not codes or a.split('-',1)[0]in codes)}
    for code in codes:
        variants=[(n,a)for n,a in catalog if a.split('-',1)[0]==code]
        if len(variants)>1:
            names=re.findall(r'[A-Za-z]{3,}',labels.get(code,''))
            variants=[(n,a)for n,a in variants if names and all(name.casefold()in a.casefold()for name in names)]
        if len(variants)!=1:raise ValueError('Номер артикула соответствует нескольким вариантам; нужен точный вариант товара, не выбор РК или ставки.')
        selected.add(variants[0][0])
    if not selected:raise ValueError('В исходном сообщении не удалось однозначно определить варианты товаров.')
    if len(selected)>50:raise ValueError('В одном тестовом плане поддерживается до 50 товаров.')
    return sorted(selected)

def prepare(w,job,ids,source_question_job_id=None,maximum_count=None,seed_nm_ids=()):
    from china_new_ads import REQUEST
    from china_group_permissions import allowed
    if not allowed(w,job):return 'Подготовить предложение могут действующие участники группы.'
    text=job.get('request_text','');m=next((x for x in job.get('tool_trace',[]) if x.get('name')=='china_saved_question'),{})
    prior=w.get(REQUEST+str(job['id']))
    if prior:
        if prior.get('nm_ids',[])!=ids:raise ValueError('Preparation request scope changed')
        return 'Подготовка этого предложения уже принята. Повторный расчёт или запуск не создаю.'
    scope=(' До '+str(maximum_count)+' товаров.' if maximum_count else '')
    request=dict(status='pending',job_id=job['id'],chat_id=job['chat_id'],sender_id=job['sender_id'],reply_message_id=m.get('message_id'),request_text='Подготовь рекламный тест.'+scope+' '+text,created_at=w.now.isoformat(),nm_ids=list(ids),seed_nm_ids=list(seed_nm_ids),maximum_count=maximum_count,source_reply_message_id=m.get('reply_message_id'),source_question_job_id=source_question_job_id,original_request_text=text,paid_model_calls=0,grants_action_permission=False)
    if not w.save(REQUEST+str(job['id']),request,insert=True):raise ValueError('Preparation request claim lost')
    return ('Подготовлю предложение примерно до '+str(maximum_count)+' товаров, если расчёты подтвердят кандидатов. ' if maximum_count else 'Подготовлю после расчётов конкретный план. ')+'Сам подберу РК, размещение, ставки и бюджет, проверю экономику и наличие. Пришлю на отдельное подтверждение; это только подготовка, без запуска и пополнений.'

def handle(w,job):
    from china_new_ads import handle as existing,REQUEST,BIND
    from china_ad_proposal_consent import handle as consent,ask
    consent_reply=consent(w,job)
    if consent_reply is not None:return consent_reply
    text=job.get('request_text','')
    marker=next((x for x in job.get('tool_trace',[]) if x.get('name')=='china_saved_question'),{})
    # An exact delivered PNG retains its original confirmation grammar and expiry.
    if w.get(BIND+str(marker.get('reply_message_id'))):
        result=existing(w,job,[])
        if result is not None:return result[0]
    if not re.search(r'реклам|тестов.*вариант',text,re.I):return None
    if not re.search(r'подбер|подоб|предлож|подготов|сделай|покаж|пришли|найди|добав|запуст|запуск',text,re.I):return None
    # Questions and negative commands cannot create a report or authorize a test.
    if re.search(r'не\s+(?:запускай|добавляй|готовь)|отмени|останови',text,re.I):
        return 'Нового запуска не будет. Для отмены уже действующего плана укажите его конкретный PNG.'
    if re.search(r'запустил|запущен',text,re.I) and not re.search(r'если.*(?:запусти|добавь)|то\s+запусти',text,re.I):
        return 'Само предложение теста не подтверждает запуск. Для запуска нужен актуальный PNG с составом, ставками и бюджетом и подтверждение ответом на него.'
    try:ids=requested_ids(w,job,text)
    except ValueError as exc:return str(exc)
    from china_group_permissions import allowed
    if not allowed(w,job):return 'Подготовить предложение могут действующие участники группы.'
    if re.search(r'добав|запуст|запуск',text,re.I) and not re.search(r'подготов|рассчита|предложение',text,re.I):
        return ask(w,job,ids)
    return prepare(w,job,ids)


