"""Exact compact price report delivery with durable receipts and reply binding.

No price executor is imported or called. Unknown Telegram outcomes are never replayed.
"""
import base64,hashlib,json,os,re
from datetime import datetime,timedelta,timezone

PATTERN=r'(?m)^(Повышение|Снижение) · (.+?) Продавец: ([^\n]+)\nПокупатель: ([^\n]+)'

def rows(answer):
    return [list(m.groups()) for m in re.finditer(PATTERN,answer)]

def deliver(w):
    import requests
    from china_cloud_cost_control import Cache,stamp
    from china_table_png import render
    c=Cache();answer=w.job['answer']
    mode=getattr(w,'mode','morning');day=str(w.day)
    root='china_agent:price_delivery:v2:'+day+':'+mode
    prepared=c.get(root+':prepared')
    if not prepared:
        from china_price_current_check import check
        try:checked=check(w,answer)
        except (RuntimeError,ValueError,KeyError) as exc:
            w.audit['current_price_check_blocker']=str(exc)[:200]
            checked='Повышение: проверка не завершена\n\nСнижение: проверка не завершена'
        if checked!=answer:
            saved=w.patch(dict(answer=checked))
            if len(saved)!=1:raise RuntimeError('Price preflight freeze lost lease')
            w.job=dict(w.job,answer=checked);answer=checked
    offers=rows(answer);scope=hashlib.sha256(answer.encode()).hexdigest()
    if prepared and prepared['answer_sha256']!=scope:raise RuntimeError('Frozen price report changed')
    parts=[]
    if len(offers)>5:
        pictures=render(['Действие','Арт','Цена продавца','Цена покупателя (новая — прогноз)'],offers,title='Китай · рекомендации по ценам · '+w.day.strftime('%d.%m.%Y'))
        if isinstance(pictures,bytes):pictures=[pictures]
        for pic in pictures:
            data=pic['bytes'] if isinstance(pic,dict) else pic
            parts.append(dict(method='sendPhoto',b64=base64.b64encode(data).decode(),sha256=hashlib.sha256(data).hexdigest()))
    else:
        parts=[dict(method='sendMessage',text=answer)]
    if not prepared:
        prepared=dict(status='prepared',answer_sha256=scope,answer=answer,parts=parts,selection_count=len(offers),expires_at=datetime.combine(w.day+timedelta(days=1),datetime.min.time(),w.now.tzinfo).isoformat(),execution_authorized=False,wb_writes=0)
        from china_price_buttons import prepare as prepare_buttons
        markup,registry=prepare_buttons(answer,offers,w.job['id'],day,prepared['expires_at'])
        if markup:prepared.update(reply_markup=markup,button_registry=registry)
        if not c.create(root+':prepared',prepared):raise RuntimeError('Price preparation claimed')
    if prepared.get('button_registry'):
        registry=prepared['button_registry'];old_registry=c.get(registry['key'])
        if old_registry and old_registry!=registry['payload']:raise RuntimeError('Frozen price buttons changed or revoked')
        if not old_registry and not c.create(registry['key'],registry['payload']):raise RuntimeError('Price buttons registry claim lost')
    parts=prepared['parts'];token=os.environ['CHINA_TELEGRAM_BOT_TOKEN']
    def tg(method,body,files=None):
        try:
            response=w.original_http(requests.Session(),'POST','https://api.telegram.org/bot'+token+'/'+method,data=body,files=files,timeout=60)
            value=response.json()
        except Exception:
            w.uncertain=True;raise RuntimeError('Telegram delivery outcome uncertain') from None
        if not response.ok or value.get('ok') is not True:
            if response.status_code==429:w.telegram_cooldown=max(1,int(value.get('parameters',{}).get('retry_after',60)))
            if response.status_code>=500:w.uncertain=True
            raise RuntimeError('Telegram rejected price report: '+str(response.status_code))
        return value['result']
    me=tg('getMe',{})
    if me.get('id')!=8780468043 or w.chat!=-1004342917488:raise RuntimeError('Price report recipient mismatch')
    message_ids=[];receipts=[]
    for i,part in enumerate(parts):
        key=root+':part:'+str(i);old=c.get(key)
        if old:
            if old.get('status')!='sent' or not old.get('message_id'):raise RuntimeError('Existing price delivery needs review; no replay')
            receipt=old['receipt']
        else:
            if not c.create(key,dict(status='sending',answer_sha256=scope,started_at=stamp(),job_id=w.job['id'])):raise RuntimeError('Price delivery claimed')
            try:
                body=dict(chat_id=w.chat);files=None
                if prepared.get('reply_markup'):body['reply_markup']=json.dumps(prepared['reply_markup'],ensure_ascii=False)
                if part['method']=='sendPhoto':
                    data=base64.b64decode(part['b64'],validate=True)
                    if hashlib.sha256(data).hexdigest()!=part['sha256']:raise RuntimeError('Price PNG changed')
                    body['caption']='Китай · цены · '+w.day.strftime('%d.%m.%Y')+'. Подтвердите кнопкой под отчётом или ответом «Сделай всё». Новая цена покупателя — прогноз.'
                    files={'photo':('prices.png',data,'image/png')}
                else:
                    body['text']=part['text']
                    from china_agent.price_brief import plain_payload
                    entities=plain_payload(answer,w.get('china_agent:prices:v1')) or {}
                    for k,v in entities.items():
                        if k!='reply_markup':body[k]=json.dumps(v,ensure_ascii=False)
                receipt=tg(part['method'],body,files)
                if receipt.get('chat',{}).get('id')!=w.chat or type(receipt.get('message_id'))is not int:
                    w.uncertain=True;raise RuntimeError('Telegram price receipt mismatch')
                c.put(key,dict(status='sent',receipt=receipt,message_id=receipt['message_id'],sent_at=stamp(),answer_sha256=scope,job_id=w.job['id']))
            except Exception as exc:
                c.put(key,dict(status='uncertain' if w.uncertain else 'failed',error=str(exc),at=stamp(),job_id=w.job['id']))
                raise
        mid=receipt['message_id'];message_ids.append(mid);receipts.append(key)
        # Bind the exact complete answer to every delivered report part.
        c.put('china_agent:price_report_message:v1:'+str(mid),dict(status='sent',chat_id=w.chat,bot_id=me['id'],message_id=mid,report_job_id=w.job['id'],report_date=day,report_sha256=scope,expires_at=prepared['expires_at'],receipt_key=key,selection_count=len(offers),execution_authorized=False))
    trace=[e for e in w.job.get('tool_trace',[]) if e.get('name')!='china_report_delivery']+[dict(name='china_report_delivery',sent_parts=len(message_ids),message_ids=message_ids,receipt_keys=receipts,report_sha256=scope)]
    saved=w.patch(dict(status='done',completed_at=stamp(),lease_until=None,error=None,tool_trace=trace))
    if len(saved)!=1:raise RuntimeError('Price delivery completion lost lease')
    c.put(root,dict(status='sent',job_id=w.job['id'],message_ids=message_ids,receipt_keys=receipts,answer_sha256=scope,completed_at=stamp(),wb_writes=0))
    w.audit.update(status='delivered',sent_parts=len(message_ids),telegram_message_ids=message_ids)

def install(root):
    from pathlib import Path
    path=Path(root)/'china_agent/daily_report_worker.py';text=path.read_text(encoding='utf-8')
    marker='            # compact_price_delivery_receipts_v2\n'
    if marker in text:return
    start=text.index('            import business_agents.conversation as conv\n')
    end=text.index('        except Exception:\n',start)
    text=text[:start]+marker+'            from china_price_delivery import deliver\n            deliver(self)\n'+text[end:]
    path.write_text(text,encoding='utf-8')

