"""Replace only a privately approved dated China morning report; no WB access."""
import os,json,hashlib,sys
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import requests

KEY='china_agent:approved_corrected_reports:2026-10-17:1502'
SOURCE='china_agent:approved_reports_resend:2026-10-17:1414'
DAY='2026-10-17'

def validate(p):
    if p.get('report_date')!=DAY or p.get('wb_writes')!=0:raise RuntimeError('Invalid replacement scope')
    if not isinstance(p.get('chat_id'),int) or not isinstance(p.get('owner_user_id'),int):raise RuntimeError('Recipient missing')
    messages=p.get('messages')
    if not isinstance(messages,list) or not messages or messages[0].get('section')!='raise':raise RuntimeError('Report parts missing')
    sections=[m.get('section') for m in messages]
    if set(sections)!={'raise','lower','control'} or sections!=sorted(sections,key={'raise':0,'lower':1,'control':2}.get):raise RuntimeError('Report order mismatch')
    if any(not isinstance(m.get('text'),str) or not 1<=len(m['text'])<=3900 or 'н/д' in m['text'] for m in messages):raise RuntimeError('Invalid report text')
    ids=p.get('old_message_ids')
    if not isinstance(ids,list) or len(ids)!=len(set(ids)) or not all(isinstance(x,int) for x in ids):raise RuntimeError('Invalid deletion scope')
    if p.get('telegram_pending'):raise RuntimeError('Unconfirmed Telegram attempt; manual reconciliation required')


def render_control(v):
    if v.get('model_version')!='wb_four_day_baseline_daily_means_v3' or v.get('report_date')!=DAY or v.get('wb_writes')!=0:
        raise RuntimeError('Corrected model not verified')
    f=lambda x:format(x,'.2f').replace('.',',')
    blocks=['Китай · контроль повышения цен · 17.10.2026\nИсправленный отчёт. База: четыре полных дня 11–14 октября. После повышения: 16 октября. Сравниваем средние за день. День изменения исключён.']
    for i in v['products']:
        a,b=i['before'],i['after']
        if a['days']!=4 or a['period_from']!='2026-10-11' or a['period_to']!='2026-10-14' or b['days']!=1 or b['period_to']!='2026-10-16':
            raise RuntimeError('Unexpected comparison period')
        rate=f(i['buyout_percent'])+'%'
        rate+=(' — принято для расчёта; собственной завершённой статистики нет.' if i['buyout_fallback'] else '; завершённых исходов: '+str(i['buyout_sample'])+'. Выборка мала.' if i['buyout_sample']<10 else '; завершённых исходов: '+str(i['buyout_sample'])+'.')
        lines=[i['article']+' · '+f(i['before_price'])+' → '+f(i['after_price'])+' ¥','Базовый выкуп: '+rate]
        for title,p in [('До повышения, 11–14 октября',a),('После повышения, 16 октября',b)]:
            daily=p.get('daily',[])
            orders=' / '.join(str(d['orders']) for d in daily)
            lines += [title+':','• Заказы: '+orders+'; всего '+str(p['orders'])+'; среднее '+f(p['orders_per_day'])+'/день; отмены '+str(sum(d.get('cancelled',0) for d in daily))+'.']
            if p['views'] is None:lines+=['• История конверсии не возвращена.']
            else:lines+=['• Конверсия периода: '+(f(p['conversion']*100)+'%' if p.get('conversion') is not None else 'не рассчитывается')+' — '+str(p['funnel_orders'])+'/'+str(p['views'])+'.']
            lines+=['• Прогноз прибыли: '+f(p['expected_profit'])+' ₽ за период; '+f(p['expected_profit_per_day'])+' ₽/день.','• Реклама включена: '+f(p['advertising'])+' ₽; '+f(p['advertising_per_day'])+' ₽/день.']
        o=b.get('outcomes',{})
        lines+=['Новые исходы: выкупы '+str(o.get('paid',0))+', отмены '+str(o.get('cancelled',0))+', возвраты '+str(o.get('returned',0))+', незавершённые '+str(o.get('pending',0))+', неизвестные '+str(o.get('unknown',0))+'.']
        delta=b['expected_profit_per_day']-a['expected_profit_per_day']
        lines+=['Разница: '+f(delta)+' ₽/день.','Результат и действие: '+i['result']['result_action'],'Первая четырёхдневная оценка: '+i['assessment_date']+'.']
        blocks.append('\n'.join(lines))
    blocks.append('Общие условия\nЗаказы WB включают отмены; дубли исключены. Конверсия — воронка MPStats: сумма заказов воронки / сумма просмотров, поэтому её числитель может отличаться от заказов WB. Незавершённые и неизвестные исходы не считаются отказами.\nПрогнозы до и после используют один базовый процент выкупа. Расчёт: 12 ₽/¥, наша себестоимость, наблюдавшиеся удержания артикула, сохранённая доставка и приёмка 10 ₽. Реклама вычтена полностью. Резерв доставки сохранён на каждый заказ, включая отменённые; дополнительные возвраты продавцу и нераспределённые расходы не включены. Для 102-Zont-beige использовано собственное наблюдение доставки 94,05 ₽ плюс приёмка 10 ₽, сохранённого тарифа артикула нет.\nПосле повышения прошёл один полный день; эффект цены пока не подтверждён. Все изменения цены согласовываем.')
    messages=[];part=''
    for block in blocks:
        if len(block)>3800:raise RuntimeError('Oversized product')
        if len(part)+len(block)+2>3800:
            messages.append(dict(section='control',text=part));part=''
        part+= ('\n\n' if part else '')+block
    if part:messages.append(dict(section='control',text=part))
    return messages

def main():
    if datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()!=DAY:raise RuntimeError('Replacement date expired')
    base=os.environ['SUPABASE_URL'].rstrip('/')
    token=os.environ['SUPABASE_SECRET_KEY']
    bot=os.environ['CHINA_TELEGRAM_BOT_TOKEN']
    session=requests.Session()
    def db(method,table,params=None,body=None):
        if table not in ('telegram_api_cache','business_agent_config'):raise RuntimeError('Database scope')
        r=session.request(method,base+'/rest/v1/'+table,params=params,json=body,headers={'apikey':token,'Authorization':'Bearer '+token,'Prefer':'return=representation'},timeout=45)
        if not r.ok:raise RuntimeError('Database operation failed')
        return r.json()
    def get(key):
        rows=db('GET','telegram_api_cache',{'cache_key':'eq.'+key,'select':'payload'})
        if len(rows)!=1:raise RuntimeError('Private receipt missing')
        return rows[0]['payload']
    existing=db('GET','telegram_api_cache',{'cache_key':'eq.'+KEY,'select':'payload'})
    if existing:p=existing[0]['payload']
    else:
        source=get(SOURCE)
        if source.get('status')!='delivered' or source.get('telegram_pending'):raise RuntimeError('Source not confirmed')
        corrected=get('china_agent:daily_expected_control:2026-10-17:verify')
        p=dict(report_date=DAY,wb_writes=0,chat_id=source['chat_id'],owner_user_id=source['owner_user_id'],messages=[m for m in source['messages'] if m['section']!='control']+render_control(corrected),old_message_ids=[s['message_id'] for s in source['sent']],source_key=SOURCE,status='ready',sent=[],deleted=[],telegram_calls=0,telegram_pending=None,authorization='Owner requested replace stale reports with corrected four-day baseline reports on 2026-10-17 at 15:00 Moscow and renewed at 15:02.')
        validate(p)
        db('POST','telegram_api_cache',body={'cache_key':KEY,'payload':p})

    validate(p)
    if p['status']=='delivered':
        print(json.dumps({'status':'already_delivered','sent_parts':len(p['sent']),'wb_writes':0}));return
    if p['status'] not in ('ready','replacing'):raise RuntimeError('Replacement not ready')
    def save():
        rows=db('PATCH','telegram_api_cache',{'cache_key':'eq.'+KEY},{'payload':p})
        if len(rows)!=1:raise RuntimeError('Audit save failed')
    cfg=db('GET','business_agent_config',{'agent_id':'eq.china','select':'chat_id,owner_user_id'})
    if len(cfg)!=1 or cfg[0]['chat_id']!=p['chat_id'] or cfg[0]['owner_user_id']!=p['owner_user_id']:raise RuntimeError('Recipient config changed')
    source=get(SOURCE)
    if source.get('status')!='delivered' or source.get('chat_id')!=p['chat_id']:raise RuntimeError('Original delivery identity mismatch')
    if sorted(s['message_id'] for s in source['sent'])!=sorted(p['old_message_ids']):raise RuntimeError('Deletion IDs differ')
    def read_tg(action,body):
        r=session.post('https://api.telegram.org/bot'+bot+'/'+action,json=body,timeout=45)
        try:v=r.json()
        except ValueError:raise RuntimeError('Telegram validation unavailable') from None
        if not v.get('ok'):raise RuntimeError('Telegram recipient verification failed')
        return v['result']
    me=read_tg('getMe',{})
    chat=read_tg('getChat',{'chat_id':p['chat_id']})
    owner=read_tg('getChatMember',{'chat_id':p['chat_id'],'user_id':p['owner_user_id']})
    ownbot=read_tg('getChatMember',{'chat_id':p['chat_id'],'user_id':me['id']})
    if chat['id']!=p['chat_id'] or owner['user']['id']!=p['owner_user_id'] or owner['status'] in ('left','kicked') or ownbot['status'] in ('left','kicked'):raise RuntimeError('Recipient membership mismatch')
    p['status']='replacing'
    p['report_sha256']=hashlib.sha256(json.dumps(p['messages'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    save()
    def mutate(action,body,identity):
        p['telegram_pending']={'action':action,'identity':identity,'at':datetime.now(ZoneInfo('UTC')).isoformat()}
        save()
        # No network retries: uncertain delivery must not be duplicated.
        try:r=session.post('https://api.telegram.org/bot'+bot+'/'+action,json=body,timeout=45);v=r.json()
        except Exception:raise RuntimeError('Telegram result uncertain; no automatic repeat') from None
        p['telegram_calls']+=1
        if not v.get('ok'):
            if action=='deleteMessage' and v.get('error_code')==400 and 'message to delete not found' in str(v.get('description','')).lower():
                v={'ok':True,'result':True}
            else:
                p['status']='failed_confirmed';p['last_error']={'action':action,'code':v.get('error_code')}
                p['telegram_pending']=None;save()
                raise RuntimeError('Telegram confirmed rejection; stopped')
        if action=='deleteMessage':p['deleted'].append(identity)
        else:
            result=v['result']
            if result.get('chat',{}).get('id')!=p['chat_id'] or not isinstance(result.get('message_id'),int):raise RuntimeError('Unexpected delivery recipient')
            p['sent'].append({'part':identity,'message_id':result['message_id'],'section':p['messages'][identity]['section']})
        p['telegram_pending']=None;save()
    for mid in p['old_message_ids']:
        if mid not in p['deleted']:mutate('deleteMessage',{'chat_id':p['chat_id'],'message_id':mid},mid)
    for index,message in enumerate(p['messages']):
        if any(s['part']==index for s in p['sent']):continue
        mutate('sendMessage',{'chat_id':p['chat_id'],'text':message['text'],'disable_web_page_preview':True},index)
    if len(p['deleted'])!=len(p['old_message_ids']) or len(p['sent'])!=len(p['messages']):raise RuntimeError('Replacement incomplete')
    p['status']='delivered';p['completed_at']=datetime.now(ZoneInfo('Europe/Moscow')).isoformat();save()
    print(json.dumps({'status':'delivered','deleted':len(p['deleted']),'sent_parts':len(p['sent']),'message_ids':[s['message_id'] for s in p['sent']],'wb_writes':0}))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Avoid printing URLs, tokens or transport error details.
        print(type(exc).__name__+': replacement stopped; inspect private audit')
        sys.exit(1)
