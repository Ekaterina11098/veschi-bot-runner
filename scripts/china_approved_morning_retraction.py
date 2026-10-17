"""Retract exact delivered report IDs at owner request; never send messages."""
import os,json,hashlib,sys
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import requests

KEY='china_agent:approved_morning_retraction:2026-10-17'
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
    p=get(KEY)
    validate(p)
    if p['status']=='delivered':
        print(json.dumps({'status':'already_delivered','sent_parts':len(p['sent']),'wb_writes':0}));return
    if p['status'] not in ('ready','replacing'):raise RuntimeError('Replacement not ready')
    def save():
        rows=db('PATCH','telegram_api_cache',{'cache_key':'eq.'+KEY},{'payload':p})
        if len(rows)!=1:raise RuntimeError('Audit save failed')
    cfg=db('GET','business_agent_config',{'agent_id':'eq.china','select':'chat_id,owner_user_id'})
    if len(cfg)!=1 or cfg[0]['chat_id']!=p['chat_id'] or cfg[0]['owner_user_id']!=p['owner_user_id']:raise RuntimeError('Recipient config changed')
    source=get(p['source_key'])
    if source.get('status')!='delivered' or source.get('chat_id')!=p['chat_id']:raise RuntimeError('Original delivery identity mismatch')
    old=[x['message_id'] for x in source.get('sent',[])]
    if sorted(old)!=sorted(p['old_message_ids']):raise RuntimeError('Deletion IDs differ from delivered replacement')
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
        if action!='deleteMessage':raise RuntimeError('Only deletion is authorized')
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
    if len(p['deleted'])!=len(p['old_message_ids']) or p['sent']:raise RuntimeError('Retraction incomplete')
    p['status']='delivered';p['completed_at']=datetime.now(ZoneInfo('Europe/Moscow')).isoformat();save()
    print(json.dumps({'status':'delivered','deleted':len(p['deleted']),'sent_parts':len(p['sent']),'message_ids':[s['message_id'] for s in p['sent']],'wb_writes':0}))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Avoid printing URLs, tokens or transport error details.
        print(type(exc).__name__+': replacement stopped; inspect private audit')
        sys.exit(1)
