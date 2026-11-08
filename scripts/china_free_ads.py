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
    codes=set(re.findall(r'(?m)^\|\s*(\d+)\s*[—–-]',source))
    if any(sum(a.split('-',1)[0]==code for _,a in catalog)>1 for code in codes):
        raise ValueError('Номер артикула соответствует нескольким вариантам; нужен список с полными артикулами.')
    selected={n for n,a in catalog if a.casefold() in source.casefold() or a.split('-',1)[0] in codes}
    if not selected:raise ValueError('В исходном сообщении не удалось однозначно определить варианты товаров.')
    if len(selected)>50:raise ValueError('В одном тестовом плане поддерживается до 50 товаров.')
    return sorted(selected)

def handle(w,job):
    from china_new_ads import handle as existing,REQUEST,BIND
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
    result=existing(w,dict(job,request_text='Подготовь рекламный тест. '+text),[])
    if result is None:return None
    request=w.get(REQUEST+str(job['id']))
    if request and request.get('job_id')==job['id'] and request.get('status')=='pending':
        w.save(REQUEST+str(job['id']),request|dict(nm_ids=ids,source_reply_message_id=marker.get('reply_message_id'),original_request_text=text,paid_model_calls=0))
    return result[0]
