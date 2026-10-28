"""Exact, prospective, human-confirmed China WB seller prices.
Only public china-price-apply workflow may execute this worker, serialized globally.
No generic queue, historical approvals, RUB writes or blind POST retries.
"""
import argparse,base64,hashlib,json,os,re,time
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from urllib.parse import quote
import requests

CHAT=-1004342917488
BOT=8780468043
PREFIX='china_agent:price_recommendation_approval:v2:'
POLICY='confirmed_exact_seller_price_v1'
def now():return datetime.now(timezone.utc)
def day():return (now()+timedelta(hours=3)).date().isoformat()
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def dec(v):
    d=Decimal(str(v))
    if not d.is_finite() or d<=0:raise ValueError('Некорректная цена')
    return d
def plan(s,p):
    if (str(p.get('nmID'))!=s['nm_id'] or p.get('vendorCode')!=s['article'] or
        p.get('currencyIsoCode4217')!='CNY' or p.get('editableSizePrice') is not False):
        raise ValueError('Карточка, валюта или режим размеров изменились')
    sizes=p.get('sizes',[])
    if not sizes or len({dec(x['price']) for x in sizes})!=1 or len({dec(x['discountedPrice']) for x in sizes})!=1:
        raise ValueError('Неоднозначные цены размеров')
    current=dec(sizes[0]['discountedPrice']);target=dec(s['target_cny'])
    if current==target:return None
    if (current!=dec(s['current_cny']) or p['discount']!=s['seller_discount'] or
        dec(sizes[0]['price'])!=dec(s['base_cny']) or p.get('clubDiscount')!=s['club_discount']):
        raise ValueError('Цена или скидка уже изменились; нужен свежий отчёт')
    discount=p['discount']
    if type(discount) is not int or not 0<=discount<100:raise ValueError('Неизвестная скидка')
    factor=Decimal(100-discount)/100
    base=target/factor
    if base!=base.to_integral_value():
        # Prefer keeping the base when reversing an earlier discount-only change.
        base=dec(sizes[0]['price']);discount_value=100-target*100/base
        if discount_value!=discount_value.to_integral_value() or not 0<=discount_value<=99:
            raise ValueError('Точная согласованная цена недостижима без округления')
        discount=int(discount_value)
    if base!=base.to_integral_value() or not 1<=base<=100000000:
        raise ValueError('Недопустимая базовая цена')
    if base*Decimal(100-discount)/100!=target:raise ValueError('Несовпадение расчёта')
    return dict(nmID=int(s['nm_id']),price=int(base),discount=discount)

class IO:
    def __init__(self):
        self.url=os.environ['SUPABASE_URL'].rstrip('/')
        key=os.environ['SUPABASE_SECRET_KEY']
        self.headers={'apikey':key,'Content-Type':'application/json'}
        if not key.startswith('sb_secret_'):self.headers['Authorization']='Bearer '+key
        self.token=os.environ['WB_TOKEN_3']
        self.bot=os.environ['CHINA_TELEGRAM_BOT_TOKEN']
    def db(self,path,method='GET',body=None,prefer=None):
        r=requests.request(method,self.url+'/rest/v1/'+path,headers={**self.headers,**({'Prefer':prefer} if prefer else {})},json=body,timeout=30)
        if not r.ok:raise RuntimeError('State HTTP '+str(r.status_code))
        return r.json() if r.content else []
    def get(self,key):
        rows=self.db('telegram_api_cache?cache_key=eq.'+quote(key,safe='')+'&select=payload')
        return rows[0]['payload'] if len(rows)==1 else None
    def create(self,key,p):
        return bool(self.db('telegram_api_cache?on_conflict=cache_key','POST',dict(cache_key=key,payload=p,expires_at='2036-10-19T00:00:00Z'),'resolution=ignore-duplicates,return=representation'))
    def put(self,key,p):
        rows=self.db('telegram_api_cache?cache_key=eq.'+quote(key,safe=''),'PATCH',dict(payload=p,updated_at=now().isoformat()),'return=representation')
        if len(rows)!=1 or rows[0]['payload']!=p:raise RuntimeError('State readback mismatch')
    def wb(self,path,method='GET',body=None):
        time.sleep(.8)
        r=requests.request(method,'https://discounts-prices-api.wildberries.ru'+path,headers={'Authorization':self.token},json=body,timeout=40)
        # Never expose response text, headers or request objects containing credentials.
        if not r.ok:raise RuntimeError('WB HTTP '+str(r.status_code))
        j=r.json()
        if j.get('error'):raise RuntimeError('WB rejected request')
        return j.get('data',j)
    def prices(self,ids):
        rows=[]
        for nm in ids:
            data=self.wb('/api/v2/list/goods/filter?limit=1000&offset=0&filterNmID='+str(nm))
            found=data.get('listGoods',[])
            if len(found)!=1 or found[0].get('nmID')!=int(nm):raise ValueError('Точная карточка WB не найдена')
            rows+=found
        return {str(p['nmID']):p for p in rows}
    def tg(self,method,body):
        r=requests.post('https://api.telegram.org/bot'+self.bot+'/'+method,json=body,timeout=30)
        j=r.json()
        if not r.ok or not j.get('ok'):raise RuntimeError('Telegram unavailable')
        return j['result']
    def capability(self):
        try:
            data=self.token.split('.')[1];claims=json.loads(base64.urlsafe_b64decode(data+'='*(-len(data)%4)))
        except Exception:raise ValueError('Не удалось проверить токен WB')
        if claims.get('t') is not False or claims.get('exp',0)<=time.time() or not (int(claims.get('s',0))&(1<<3)) or int(claims.get('s',0))&(1<<30):
            raise ValueError('Токен WB не разрешает запись цен или просрочен')
        rows=self.db("analytics_snapshots?cabinet=eq.token_3&source=eq.seller_identity&status=eq.complete&select=payload&limit=100")
        sids={r['payload'].get('sid') for r in rows}
        if len(sids)!=1 or claims.get('sid') not in sids:raise ValueError('Кабинет WB не подтверждён')
        self.wb('/ping')
        return dict(write_scope=True,identity_verified=True,wb_writes=0)
    def validate(self,a):
        cfg=self.db('business_agent_config?agent_id=eq.china&select=active,chat_id,bot_id')
        if len(cfg)!=1 or not cfg[0]['active'] or cfg[0]['chat_id']!=CHAT or cfg[0]['bot_id']!=BOT:raise ValueError('Конфигурация Китая изменилась')
        member=self.tg('getChatMember',dict(chat_id=CHAT,user_id=a['actor_user_id']))
        if (member.get('user',{}).get('id')!=a['actor_user_id'] or member['user'].get('is_bot') or
            not (member.get('status') in ['member','administrator','creator'] or member.get('status')=='restricted' and member.get('is_member') is True)):
            raise ValueError('Подтвердивший больше не участник группы')
        rows=self.db('business_agent_jobs?id=eq.'+str(int(a['report_job_id']))+'&agent_id=eq.china&chat_id=eq.'+str(CHAT)+'&status=eq.done&select=answer,request_text,tool_trace')
        if len(rows)!=1:raise ValueError('Отчёт не найден')
        j=rows[0]
        if a.get('basis')=='explicit_zero_order_percent':
            from china_zero_order_price_command import validate_command
            validate_command(self,a,j);return
        if j['request_text'] not in ['/china_morning_pair_candidates','/china_price_intraday_raise'] or sha(j['answer'])!=a['report_sha256']:raise ValueError('Отчёт изменился')
        if not any(t.get('name')=='china_price_daily_report' and t.get('report_date')==a['report_date'] for t in j['tool_trace']):raise ValueError('Дата отчёта не подтверждена')
        for s in a['selections']:
            def fmt(v):return format(dec(v).normalize(),'f').replace('.',',')
            expected=s['action']+' · '+s['article']+' Продавец: '+fmt(s['current_cny'])+' → '+fmt(s['target_cny'])+' ¥'
            if expected not in j['answer'].splitlines():raise ValueError('Согласованные цены отсутствуют в отчёте')

def validate_approval(key,a):
    if not re.fullmatch(re.escape(PREFIX)+r'-1004342917488:\d+:\d+:[0-9a-f]{64}',key):raise ValueError('Invalid approval key')
    if not a or a.get('schema_version')!=2 or a.get('execution_authorized') is not True or a.get('execution_policy')!=POLICY or a.get('approval_policy')!='all_current_human_group_members' or a.get('decision')!='approved_recommendation' or a.get('chat_id')!=CHAT or a.get('bot_id')!=BOT:
        raise ValueError('Нет нового разрешения на применение WB')
    age=(now()-datetime.fromisoformat(a['created_at'].replace('Z','+00:00'))).total_seconds()
    if a.get('report_date')!=day() or not 0<=age<=86400:raise ValueError('Подтверждение устарело')
    ss=a.get('selections',[])
    if not 1<=len(ss)<=100 or len({s['nm_id'] for s in ss})!=len(ss):raise ValueError('Неоднозначный выбор')
    for s in ss:
        old=dec(s['current_cny']);new=dec(s['target_cny'])
        if s['action'] not in ['Повышение','Снижение'] or (new>old)!=(s['action']=='Повышение') or new==old:raise ValueError('Неверное направление')
    parts=key[len(PREFIX):].split(':')
    if parts[1]!=str(a['report_job_id']) or parts[2]!=str(a['actor_user_id']):raise ValueError('Approval identity mismatch')

def process(io,key,polls=45,pause=time.sleep):
    a=io.get(key);validate_approval(key,a)
    execution='china_agent:price_execution:v1:'+key[len(PREFIX):]
    e=io.get(execution)
    if e and e.get('status') in ['done','blocked','uncertain','failed']:return e
    io.validate(a);io.capability()
    if not e:
        e=dict(status='preflight',approval_key=key,actor_user_id=a['actor_user_id'],created_at=now().isoformat(),items=[])
        if not io.create(execution,e):return io.get(execution)
    if e['status']=='submitting':
        e['status']='uncertain';e['reason']='Отправка WB могла пройти, квитанция не сохранена. Автоповтор заблокирован.'
        io.put(execution,e);return e
    if e['status']=='preflight':
        fresh=io.prices([s['nm_id'] for s in a['selections']])
        for s in a['selections']:
            old_item=next((x for x in e['items'] if x['selection']['nm_id']==s['nm_id']),None)
            if old_item:continue
            try:
                request=plan(s,fresh[s['nm_id']])
                lock='china_agent:price_write_lock:v1:'+s['nm_id']
                previous=io.get(lock)
                if previous and previous.get('execution')!=execution and previous.get('status') in ['submitting','submitted','uncertain']:
                    raise ValueError('Для товара есть незавершённая запись WB; повтор заблокирован')
                item=dict(selection=s,request=request,status='ready' if request else 'already_at_target')
                if request:
                    state=dict(execution=execution,status='submitting',selection=s,created_at=now().isoformat())
                    if previous:io.put(lock,state)
                    elif not io.create(lock,state):raise ValueError('Товар уже занят другим подтверждением')
                    item['lock']=lock
                e['items'].append(item)
            except ValueError as ex:e['items'].append(dict(selection=s,status='blocked',reason=str(ex)))
            io.put(execution,e)
        # Revalidate every ready item after recovery, including a crash during preflight.
        for x in e['items']:
            if x['status']=='ready':
                try:
                    checked=plan(x['selection'],fresh[x['selection']['nm_id']])
                    if checked!=x['request']:raise ValueError('Цена изменилась во время подготовки')
                except ValueError as ex:
                    x['status']='blocked';x['reason']=str(ex)
                    io.put(x['lock'],dict(execution=execution,status='done',reason=str(ex)))
        requests_body=[x['request'] for x in e['items'] if x['status']=='ready']
        if not requests_body:
            e['status']='done';io.put(execution,e);return e
        e['request']=dict(data=requests_body);e['status']='submitting';io.put(execution,e)
        # Single non-retriable write. State is durable BEFORE crossing remote boundary.
        try:
            result=io.wb('/api/v2/upload/task','POST',e['request'])
            task=result.get('id')
            if type(task) is not int or task<=0:raise RuntimeError('Missing WB upload ID')
            e['upload_id']=task;e['upload_response']=result;e['status']='submitted';io.put(execution,e)
        except Exception:
            e['status']='uncertain';e['reason']='Результат отправки WB неизвестен. Повтор заблокирован; требуется сверка владельцем.'
            io.put(execution,e);return e
    if e['status']=='submitted':
        for _ in range(polls):
            try:
                state=io.wb('/api/v2/history/tasks?uploadID='+str(e['upload_id']))
                if state.get('uploadID')!=e['upload_id']:raise RuntimeError('Task identity mismatch')
                e['wb_state']=state;io.put(execution,e)
                if state.get('status') in [3,4,5,6]:
                    details=io.wb('/api/v2/history/goods/task?uploadID='+str(e['upload_id'])+'&limit=1000&offset=0')
                    if details.get('uploadID')!=e['upload_id']:raise RuntimeError('Details identity mismatch')
                    e['wb_details']=details
                    fresh=io.prices([x['selection']['nm_id'] for x in e['items'] if x['status']=='ready'])
                    for x in e['items']:
                        if x['status']!='ready':continue
                        s=x['selection'];p=fresh[s['nm_id']]
                        goods=[g for g in details.get('historyGoods',[]) if str(g.get('nmID'))==s['nm_id']]
                        errors=[g.get('errorText') for g in goods if g.get('errorText')]
                        applied=(state['status'] in [3,5] and goods and not errors and
                            p.get('vendorCode')==s['article'] and p.get('currencyIsoCode4217')=='CNY' and
                            p.get('discount')==x['request']['discount'] and p.get('clubDiscount')==s['club_discount'] and
                            p.get('sizes') and all(dec(z['price'])==dec(x['request']['price']) and dec(z['discountedPrice'])==dec(s['target_cny']) for z in p['sizes']))
                        x['status']='applied' if applied else 'failed'
                        x['readback']=p;x['errors']=errors
                        io.put(x['lock'],dict(execution=execution,status='done' if applied else 'uncertain',upload_id=e['upload_id'],readback=p))
                    e['status']='done';e['completed_at']=now().isoformat();io.put(execution,e);return e
            except Exception:e['last_check']='WB readback temporarily unavailable';io.put(execution,e)
            pause(15)
        e['reason']='WB ещё обрабатывает загрузку или сверка недоступна. Новая запись не отправлялась.'
        io.put(execution,e)
    return e

def notify(io,key,e):
    nk='china_agent:price_execution_notice:v1:'+sha(key+':'+e['status'])
    if not io.create(nk,dict(status='sending',execution_status=e['status'],created_at=now().isoformat())):return
    lines=[]
    for x in e.get('items',[]):
        s=x['selection'];status={'applied':'применено и проверено','already_at_target':'уже установлена','blocked':'не изменено: '+x.get('reason',''),'failed':'не подтверждено WB, требуется сверка','ready':'ожидает проверки WB'}[x['status']]
        lines.append(s['article']+': '+s['current_cny'].replace('.',',')+' → '+s['target_cny'].replace('.',',')+' ¥ — '+status)
    text='Результат подтверждения цен\n'+'\n'.join(lines)
    if e.get('reason'):text+='\n'+e['reason']
    # bound maximum output: a single result message to avoid partial retries.
    if len(text)>3900:text=text[:3500]+'\nПолный результат сохранён в журнале; список сокращён.'
    try:
        r=io.tg('sendMessage',dict(chat_id=CHAT,text=text,link_preview_options=dict(is_disabled=True)))
        if r.get('chat',{}).get('id')!=CHAT or type(r.get('message_id')) is not int:raise RuntimeError('Receipt mismatch')
        io.put(nk,dict(status='sent',message_id=r['message_id'],chat_id=CHAT,sent_at=now().isoformat(),text=text))
    except Exception:io.put(nk,dict(status='uncertain',execution_status=e['status']))

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify',action='store_true');p.add_argument('--approval-key',default='');args=p.parse_args()
    io=IO()
    if args.verify:
        result=io.capability()
        cfg=io.db('business_agent_config?agent_id=eq.china&select=chat_id,bot_id,active')
        if cfg!=[dict(chat_id=CHAT,bot_id=BOT,active=True)]:raise ValueError('Configuration mismatch')
        print(json.dumps(result));return
    if os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch' or os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':
        raise ValueError('Only explicit public main dispatch may apply WB prices')
    # GitHub replaces a third pending run in a concurrency group. Drain durable
    # same-day confirmations too, so overlapping participants cannot lose intent.
    keys=[args.approval_key]
    validate_approval(keys[0],io.get(keys[0]))
    queued=io.db('telegram_api_cache?cache_key=like.china_agent:price_recommendation_approval:v2:*&payload->>report_date=eq.'+day()+'&select=cache_key&order=updated_at.asc&limit=100')
    keys+= [r['cache_key'] for r in queued if r['cache_key'] not in keys]
    started=time.monotonic()
    for key in keys:
        if time.monotonic()-started>900:break
        try:e=process(io,key,polls=8)
        except ValueError as ex:
            a=io.get(key);validate_approval(key,a)
            e=dict(status='blocked',reason=str(ex),items=[])
            ek='china_agent:price_execution:v1:'+key[len(PREFIX):]
            old=io.get(ek)
            if old and old.get('status') in ['submitting','submitted','uncertain']:
                e=old
            elif old:io.put(ek,e)
            else:io.create(ek,e)
        except Exception:
            # Preserve any boundary-crossing status and notify without retrying POST.
            ek='china_agent:price_execution:v1:'+key[len(PREFIX):]
            e=io.get(ek) or dict(status='blocked',items=[])
            e['reason']='Технический сбой проверки. Результат не подтверждён; повторная запись автоматически не отправлялась.'
            if io.get(ek):io.put(ek,e)
            else:io.create(ek,e)
        notify(io,key,e)
        print(json.dumps(dict(status=e['status'],upload_id=e.get('upload_id'),items=len(e.get('items',[]))),ensure_ascii=False))
if __name__=='__main__':main()
