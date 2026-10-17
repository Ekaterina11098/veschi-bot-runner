"""Owner-scoped China conversion watches; read-only MPStats and durable TG receipts."""
import argparse
import hashlib
import json
import math
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MSK = ZoneInfo('Europe/Moscow')
PREFIX = 'china_agent:conversion_watch:v1:'
DAILY = 'china_agent:conversion_watch_day:v1:'
RECEIPTS = 'china_agent:conversion_watch_delivery:v1:'
HELP = ('Пример: «Следи за конверсией 52-NoelBag-fuchsia за последние 5 дней, '
        'присылай ежедневно в 12:00 МСК». Список: «Мои наблюдения». '
        'Изменить: «Измени наблюдение ID на 13:00 за последние 4 дня». '
        'Отменить: «Отмени наблюдение ID».')


def intent(text):
    value = text.casefold().replace('ё', 'е')
    if 'наблюден' in value:
        if re.search(r'\b(отмени|отменить|останови|удали)\b', value): return 'cancel'
        if re.search(r'\b(измени|изменить|перенеси|перенести)\b', value): return 'update'
        if re.search(r'\b(мои|список|покажи|какие)\b', value): return 'list'
    if 'конверс' in value and re.search(r'\b(следи|отслеживай|отслеживать|отследи|наблюдай|ежедневно|каждый день)\b', value):
        if re.search(r'\b(можно ли|умеешь ли|как|например)\b', value): return 'help'
        return 'create'
    return None


def parameters(text):
    value = text.casefold().replace('ё', 'е')
    if re.search(r'\b(ип|ооо)\b', value): raise ValueError('Наблюдения этого бота доступны только для кабинета Китай.')
    if re.search(r'\b(utc|gmt|берлин|немецк)', value): raise ValueError('Укажи время по Москве, например 12:00 МСК.')
    times = re.findall(r'(?<![\w-])(\d{1,2})\s*[:\-]\s*(\d{2})(?![\w-])', value)
    if len(times) > 1: raise ValueError('Укажи одно время ежедневного отчёта по Москве.')
    clock = None
    if times:
        h, m = map(int, times[0])
        if h > 23 or m > 59: raise ValueError('Время должно быть от 00:00 до 23:59 МСК.')
        clock = f'{h:02}:{m:02}'
    periods = re.findall(r'(?:последни[ехй]+|период\s*|за)\s+(\d+)\s+(?:полн\w+\s+)?дн(?:ей|я|и|ь)', value)
    if len(set(periods)) > 1: raise ValueError('Укажи один период: например последние 5 полных дней.')
    days = int(periods[0]) if periods else None
    if days is not None and not 1 <= days <= 14: raise ValueError('Поддерживается от 1 до 14 полных дней.')
    return clock, days


def next_due(clock, now):
    h, m = map(int, clock.split(':'))
    local = now.astimezone(MSK)
    target = local.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= local: target += timedelta(days=1)
    return target.astimezone(timezone.utc).isoformat()


def count(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or int(value) != value:
        raise ValueError('Unknown funnel counter')
    return int(value)


def unpack(observation, day, nm, article):
    if observation.get('scope_verified') is not True or observation.get('status') != 'received': return None
    args = observation.get('arguments') or {}
    if str(args.get('date_from')) != day or str(args.get('date_to')) != day or args.get('start_row') != 0: return None
    body = (observation.get('data') or {}).get('data') or {}
    rows = body.get('data')
    if not isinstance(rows, list) or body.get('total') != len(rows) or body.get('need_update') != 0: return None
    if len({r.get('p_id') for r in rows}) != len(rows): return None
    matches = [r for r in rows if str(r.get('nm_id')) == str(nm)]
    if len(matches) != 1 or str(matches[0].get('sa_name', '')).casefold() != article.casefold(): return None
    r = matches[0]
    try: views, orders = count(r.get('open_card_count')), count(r.get('funnel_orders_count'))
    except ValueError: return None
    return dict(date=day, views=views, orders=orders, source='MPStats', cabinet='token_3', nm_id=str(nm), article=article)


def report(watch, daily, now):
    end = now.astimezone(MSK).date() - timedelta(days=1)
    days = [(end-timedelta(days=i)).isoformat() for i in range(watch['days']-1, -1, -1)]
    lines = ['Китай · конверсия · '+watch['article'], 'Наблюдение '+watch['id']+' · '+days[0]+'–'+days[-1]+' · полные дни МСК']
    known = []
    for d in days:
        row = daily.get(d)
        if row is None: lines.append(d+': данные не получены.'); continue
        known.append(row)
        cr = f"{100*row['orders']/row['views']:.2f}%".replace('.', ',') if row['views'] else 'не определяется: нет просмотров'
        lines.append(d+': '+cr+f" — {row['orders']} заказов воронки / {row['views']} просмотров.")
    if len(known) == len(days):
        views, orders = sum(r['views'] for r in known), sum(r['orders'] for r in known)
        lines.append('За период: '+(f'{orders/views:.2%}'.replace('.', ',') if views else 'конверсия не определяется')+f' ({orders}/{views}).')
    else: lines.append('Отчёт неполный: '+str(len(days)-len(known))+' дн. без данных. Пропуски не считаются нулями; следующий отчёт проверит их снова.')
    a, b = daily.get(days[-2]) if len(days)>1 else None, daily.get(days[-1])
    if a and b and a['views'] and b['views']:
        delta = 100*(b['orders']/b['views']-a['orders']/a['views'])
        lines.append('К предыдущему дню: '+f'{delta:+.2f}'.replace('.', ',')+' п.п. Изменение описательное; причина не установлена.')
    lines += ['Источник: MPStats. Заказы воронки могут отличаться от заказов WB. Итог — отношение сумм, не среднее процентов.',
              'Ежедневно в '+watch['clock']+' МСК. Отмена: «Отмени наблюдение '+watch['id']+'».']
    return '\n'.join(lines)


class Worker:
    def __init__(self, db, transport, now=None, collect=None):
        self.db, self.transport = db, transport
        self.now = now or datetime.now(timezone.utc)
        self.collect = collect
        self.cfg = None

    def get(self, key):
        rows = self.db('GET', 'telegram_api_cache', params={'cache_key':'eq.'+key,'select':'payload','limit':1}) or []
        return rows[0]['payload'] if rows else None

    def save(self, key, value, insert=False):
        rows = self.db('POST', 'telegram_api_cache', params={'on_conflict':'cache_key'},
            body=dict(cache_key=key,payload=value,updated_at=self.now.isoformat(),expires_at=(self.now+timedelta(days=3650)).isoformat()),
            prefer=('resolution=ignore-duplicates' if insert else 'resolution=merge-duplicates')+',return=representation') or []
        return bool(rows)

    def config(self):
        rows = self.db('GET','business_agent_config',params={'agent_id':'eq.china','active':'eq.true','select':'agent_id,chat_id,owner_user_id,bot_id','limit':1}) or []
        if len(rows)!=1: raise RuntimeError('China config unavailable')
        return rows[0]

    def authorized(self, obj):
        cfg=self.config()
        return obj.get('agent_id')=='china' and obj.get('chat_id')==cfg['chat_id'] and obj.get('owner_user_id',obj.get('sender_id'))==cfg['owner_user_id']

    def watches(self):
        cfg=self.config()
        rows=self.db('GET','telegram_api_cache',params={'cache_key':'like.'+PREFIX+str(cfg['chat_id'])+':'+str(cfg['owner_user_id'])+':*','select':'cache_key,payload','limit':100}) or []
        if len(rows)>=100:raise RuntimeError('Watch list truncated')
        return [(r['cache_key'],r['payload']) for r in rows if self.authorized(r['payload'])]

    def catalog(self):
        from business_agents.data import Data
        snap=Data('china',lambda t,p:self.db('GET',t,params=p)).snapshot('cards','token_3')
        if not snap.get('available'):raise ValueError('Сохранённый каталог Китая недоступен; артикул не подтверждён.')
        return [(str(r['nmID']),str(r['vendorCode'])) for r in snap['rows'] if r.get('nmID') and r.get('vendorCode') and not Data.excluded(r['vendorCode'])]

    def resolve(self, text):
        value=text.casefold()
        found=[(nm,a) for nm,a in self.catalog() if re.search(r'(?<![\w-])'+re.escape(a.casefold())+r'(?![\w-])',value)]
        if len(found)!=1:raise ValueError('Укажи один точный артикул из кабинета Китай. '+HELP)
        return found[0]

    def command(self, job):
        if not self.authorized(job):raise PermissionError('Owner scope mismatch')
        text=job['request_text']; action=intent(text)
        if action=='help':return HELP
        watches=self.watches()
        if action=='list':
            active=[w for _,w in watches if w['status']=='active']
            return ('Активных наблюдений нет. '+HELP) if not active else 'Наблюдения Китай:\n'+'\n'.join(w['id']+' · '+w['article']+' · '+str(w['days'])+' дн. · '+w['clock']+' МСК' for w in active)
        if action in ('cancel','update'):
            selected=[(key,w) for key,w in watches if re.search(r'(?<![\w-])'+re.escape(w['id'])+r'(?![\w-])',text.casefold()) or w['article'].casefold() in text.casefold()]
            if len(selected)!=1:raise ValueError('Укажи ID или точный артикул одного наблюдения. Напиши «Мои наблюдения».')
            key,w=selected[0]
            if w.get('last_job_id')==job['id']:return w['last_confirmation']
            if action=='cancel':
                w['status']='cancelled';answer='Наблюдение '+w['id']+' по '+w['article']+' отменено.'
            else:
                clock,days=parameters(text)
                if clock is None and days is None:raise ValueError('Укажи новое время или период. '+HELP)
                w.update(clock=clock or w['clock'],days=days or w['days'],status='active')
                w['next_at']=next_due(w['clock'],self.now)
                answer='Наблюдение '+w['id']+' обновлено: '+w['article']+', '+str(w['days'])+' полных дней, ежедневно в '+w['clock']+' МСК.'
            w.update(revision=w['revision']+1,last_job_id=job['id'],last_confirmation=answer)
            self.save(key,w);return answer
        if action!='create':return None
        clock,days=parameters(text)
        if not clock:raise ValueError('Укажи время ежедневного отчёта по Москве. '+HELP)
        nm,article=self.resolve(text)
        cfg=self.config();key=PREFIX+str(cfg['chat_id'])+':'+str(cfg['owner_user_id'])+':'+nm
        old=self.get(key)
        if old and old.get('last_job_id')==job['id']:return old['last_confirmation']
        if old and old.get('status')=='active' and old['clock']==clock and old['days']==(days or 5):
            return 'Наблюдение '+old['id']+' уже активно: '+article+', '+str(old['days'])+' полных дней, ежедневно в '+clock+' МСК. Второе наблюдение не создано.'
        if not old and sum(w['status']=='active' for _,w in watches)>=10:raise ValueError('Лимит — 10 активных наблюдений; сначала отмени ненужное.')
        watch=dict(agent_id='china',chat_id=cfg['chat_id'],owner_user_id=cfg['owner_user_id'],nm_id=nm,article=article,
            id=hashlib.sha256(key.encode()).hexdigest()[:8],days=days or 5,clock=clock,status='active',revision=(old or {}).get('revision',0)+1,
            next_at=next_due(clock,self.now),initial_pending=True,last_job_id=job['id'])
        answer='Сохранено наблюдение '+watch['id']+': '+article+' · Китай · последние '+str(watch['days'])+' полных дней. Ежедневно в '+clock+' МСК в этот чат. Первый срез пришлю отдельно.\nОтмена: «Отмени наблюдение '+watch['id']+'».'
        watch['last_confirmation']=answer
        self.save(key,watch);return answer

    def send_once(self,key,chat,text):
        receipt=self.get(RECEIPTS+key)
        if receipt and receipt.get('status') in ('sent','sending','uncertain'):return receipt['status']
        if receipt and receipt.get('retry_at') and self.now<datetime.fromisoformat(receipt['retry_at']):return 'waiting'
        if not receipt:
            receipt=dict(status='ready',chat_id=chat,text=text,created_at=self.now.isoformat())
            if not self.save(RECEIPTS+key,receipt,insert=True):return 'waiting'
        if receipt['chat_id']!=chat or receipt['text']!=text:raise RuntimeError('Delivery identity changed')
        receipt['status']='sending';self.save(RECEIPTS+key,receipt)
        try:result=self.transport(chat,text)
        except Exception:
            receipt['status']='uncertain';self.save(RECEIPTS+key,receipt);return 'uncertain'
        if not result.get('ok'):
            receipt.update(status='rejected',code=result.get('error_code'),retry_at=(self.now+timedelta(seconds=max(300,int((result.get('parameters') or {}).get('retry_after',300))))).isoformat())
            self.save(RECEIPTS+key,receipt);return 'rejected'
        message=result['result']
        if message.get('chat',{}).get('id')!=chat or not isinstance(message.get('message_id'),int):
            receipt['status']='uncertain';self.save(RECEIPTS+key,receipt);return 'uncertain'
        receipt.update(status='sent',message_id=message['message_id']);self.save(RECEIPTS+key,receipt);return 'sent'

    def jobs(self):
        rows=self.db('GET','business_agent_jobs',params={'agent_id':'eq.china','or':'(and(status.eq.pending,retry_at.lte.'+self.now.isoformat()+'),and(status.eq.running,lease_until.lte.'+self.now.isoformat()+'))','select':'*','order':'id.asc','limit':100}) or []
        processed=0
        for job in rows:
            if not intent(job['request_text']):continue
            if not self.authorized(job):continue
            lease=str(uuid.uuid4())
            filters={'id':'eq.'+str(job['id']),'status':'eq.'+job['status']}
            if job['status']=='running':filters['lease_until']='eq.'+job['lease_until']
            claimed=self.db('PATCH','business_agent_jobs',params=filters,body={'status':'running','lease_token':lease,'lease_until':(self.now+timedelta(minutes=10)).isoformat(),'attempts':job.get('attempts',0)+1},prefer='return=representation') or []
            if not claimed:continue
            def patch(body):return self.db('PATCH','business_agent_jobs',params={'id':'eq.'+str(job['id']),'lease_token':'eq.'+lease},body=body,prefer='return=representation')
            try:
                try:answer=job.get('answer') or self.command(job)
                except ValueError as exc:answer=str(exc)
                patch({'answer':answer})
                outcome=self.send_once('command:'+str(job['id']),job['chat_id'],answer)
                patch({'status':'done' if outcome in ('sent','sending','uncertain') else 'pending','error':None if outcome=='sent' else 'delivery_'+outcome,'lease_until':None,'retry_at':(self.now+timedelta(minutes=5)).isoformat(),'completed_at':self.now.isoformat() if outcome=='sent' else None})
            except Exception:
                patch({'status':'pending','error':'watch_processing_failed','lease_until':None,'retry_at':(self.now+timedelta(minutes=5)).isoformat()})
            processed+=1
            if processed>=10:break
        return processed

    def load_days(self,watch):
        end=self.now.astimezone(MSK).date()-timedelta(days=1)
        daily={};missing=[]
        for i in range(watch['days']):
            day=(end-timedelta(days=i)).isoformat();key=DAILY+watch['nm_id']+':'+day
            cached=self.get(key)
            if cached and cached.get('article')==watch['article'] and cached.get('cabinet')=='token_3' and cached.get('date')==day:
                daily[day]=cached;continue
            rows=self.db('GET','analytics_snapshots',params={'source':'in.(mpstats_lk_wb_products,mpstats_products_composed)','cabinet':'eq.token_3','status':'eq.complete','period_from':'eq.'+day,'period_to':'eq.'+day,'select':'id,payload,collected_at','order':'collected_at.desc','limit':5}) or []
            for row in rows:
                stamp=datetime.fromisoformat(row['collected_at'].replace('Z','+00:00'))
                if stamp.astimezone(MSK).date().isoformat()<=day:continue
                obs=row.get('payload')
                value=unpack(obs[0],day,watch['nm_id'],watch['article']) if isinstance(obs,list) and len(obs)==1 else None
                if value:
                    value.update(observed_at=row['collected_at'],snapshot_id=row['id']);self.save(key,value);daily[day]=value;break
            if day not in daily:missing.append(day)
        return daily,missing

    def reports(self):
        due=[(k,w) for k,w in self.watches() if w['status']=='active' and (w.get('initial_pending') or datetime.fromisoformat(w['next_at'])<=self.now)]
        if not due:return 0
        needed=set()
        for _,w in due:
            _,missing=self.load_days(w);needed.update(missing)
        if needed and self.collect:
            try:self.collect(sorted(needed,reverse=True)[:14])
            except Exception:pass  # A source outage must produce an explicit partial report.
        sent=0
        for key,w in due:
            # Stop on cancellation or chat/owner reassignment before sending.
            live=self.get(key)
            if not live or not self.authorized(live) or live['status']!='active' or live['revision']!=w['revision']:continue
            daily,_=self.load_days(w)
            label='initial:'+str(w['revision']) if w.get('initial_pending') else self.now.astimezone(MSK).date().isoformat()
            receipt_key='report:'+w['id']+':'+label
            old=self.get(RECEIPTS+receipt_key)
            text=old['text'] if old else report(w,daily,self.now)
            status=self.send_once(receipt_key,w['chat_id'],text)
            if status=='sent':
                w.update(initial_pending=False,next_at=next_due(w['clock'],self.now),last_sent_at=self.now.isoformat());self.save(key,w);sent+=1
            elif status in ('sending','uncertain'):
                w.update(status='delivery_uncertain');self.save(key,w)
        return sent


def runtime():
    import requests
    session=requests.Session();base=os.environ['SUPABASE_URL'].rstrip('/');secret=os.environ['SUPABASE_SECRET_KEY'].strip()
    def db(method,table,params=None,body=None,prefer=None):
        if table not in ('telegram_api_cache','business_agent_jobs','business_agent_config','analytics_snapshots'):raise RuntimeError('DB scope')
        headers={'apikey':secret,'Prefer':prefer or 'return=representation'}
        if not secret.startswith('sb_secret_'):headers['Authorization']='Bearer '+secret
        r=session.request(method,base+'/rest/v1/'+table,params=params,json=body,headers=headers,timeout=40)
        if not r.ok:raise RuntimeError('State HTTP '+str(r.status_code))
        return r.json() if r.content else None
    bot=os.environ['CHINA_TELEGRAM_BOT_TOKEN'].strip()
    def send(chat,text):
        # No retries after a timeout: at-most-once delivery takes precedence.
        return session.post('https://api.telegram.org/bot'+bot+'/sendMessage',json={'chat_id':chat,'text':text,'disable_web_page_preview':True},timeout=35).json()
    def collect(days):
        from analytics.mpstats_probe import discover
        from analytics.mpstats_gaps import execute_reads
        now=datetime.now(timezone.utc)
        pause=db('GET','telegram_api_cache',params={'cache_key':'eq.mpstats:cooldown','expires_at':'gt.'+now.isoformat(),'select':'cache_key','limit':1}) or []
        if pause:return
        requests_=[dict(cabinet='token_3',tool='lk_wb_products',key='conversion_watch:'+d,priority=80,arguments=dict(date_from=d,date_to=d,start_row=0,end_row=1500)) for d in days]
        def persist(cabinet,obs):
            args=obs.get('arguments') or {};d=args.get('date_from')
            if cabinet!='token_3' or d not in days or args.get('date_to')!=d:raise RuntimeError('Collection scope')
            if obs.get('retry_after'):
                db('POST','telegram_api_cache',params={'on_conflict':'cache_key'},prefer='resolution=merge-duplicates,return=representation',body={'cache_key':'mpstats:cooldown','payload':{'pending':True},'expires_at':(now+timedelta(seconds=int(obs['retry_after']))).isoformat()})
            if obs.get('status')!='received' or obs.get('scope_verified') is not True:return
            db('POST','analytics_snapshots',body=dict(source='mpstats_lk_wb_products',cabinet='token_3',run_id='conversion-watch-'+os.environ.get('GITHUB_RUN_ID','manual'),period_from=d,period_to=d,status='complete',payload=[obs],detail='Owner-requested exact completed-day conversion watch'))
        def extra(call,checks,known):return execute_reads(call,checks,known,requests_,{},persist,max_requests=len(requests_))
        # Uses the existing shared MPStats cooldown and runner serialization.
        result=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=extra)
        if result.get('retry_after'):
            db('POST','telegram_api_cache',params={'on_conflict':'cache_key'},prefer='resolution=merge-duplicates,return=representation',body={'cache_key':'mpstats:cooldown','payload':{'pending':True},'expires_at':(now+timedelta(seconds=int(result['retry_after']))).isoformat()})
    return Worker(db,send,collect=collect)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    w=runtime()
    if args.verify:
        cfg=w.config();watches=w.watches()
        print(json.dumps(dict(status='verified',config_ready=bool(cfg),active_watches=sum(x['status']=='active' for _,x in watches),telegram_calls=0,wb_writes=0)));return
    jobs=w.jobs()
    try:sent=w.reports()
    except Exception:
        # Commands stay usable during a source outage; due reports retry next tick.
        print(json.dumps(dict(status='source_pending',processed_commands=jobs,wb_writes=0)));raise
    print(json.dumps(dict(status='complete',processed_commands=jobs,sent_reports=sent,wb_writes=0)))


if __name__=='__main__':main()
