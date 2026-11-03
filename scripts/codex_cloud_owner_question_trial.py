"""Single explicit owner test question; no direct TG/WB calls."""
import os,json,time
from datetime import datetime,timezone,timedelta
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from openai import OpenAI
ROOT='china_agent:codex_bridge:v1:'
TRIAL='china_agent:codex_cloud_trial:v1:20261103:'
THREAD='01a14b40-d7b4-76b1-a8eb-9bc1eea36335'
CHAT=-1004342917488;BOT=8780468043;OWNER=5122667182
QUESTION='Облачный тест: когда оценим девять тестов?'
def stamp():return datetime.now(timezone.utc).isoformat()
def api(method,table,params=None,body=None):
    u=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/'+table
    if params:u+='?'+urlencode(params)
    secret=os.environ['SUPABASE_SECRET_KEY']
    headers={'apikey':secret,'Authorization':'Bearer '+secret,'Content-Type':'application/json',
             'Prefer':'return=representation,resolution=ignore-duplicates'}
    with urlopen(Request(u,method=method,headers=headers,data=None if body is None else json.dumps(body).encode()),timeout=25) as r:return json.load(r)
def get(key):
    rows=api('GET','telegram_api_cache',{'cache_key':'eq.'+key,'select':'payload'})
    return rows[0]['payload'] if rows else None
def once(key,value):
    api('POST','telegram_api_cache',body={'cache_key':key,'payload':value,'updated_at':stamp(),'expires_at':(datetime.now(timezone.utc)+timedelta(days=30)).isoformat()})
    if get(key)!=value:raise RuntimeError('Exact readback mismatch')
def valid(inbox,job):
    marker=next((v for v in job.get('tool_trace',[]) if v.get('name')=='china_saved_question'),{})
    return (inbox.get('request_text')==QUESTION and inbox.get('chat_id')==CHAT and inbox.get('bot_id')==BOT
      and inbox.get('thread_id')==THREAD and inbox.get('sender_id')==OWNER
      and job.get('id')==inbox.get('job_id') and job.get('chat_id')==CHAT and job.get('sender_id')==OWNER
      and job.get('request_text') in (QUESTION,'/codex '+QUESTION)
      and marker.get('codex_bridge') is True and marker.get('codex_thread_id')==THREAD
      and marker.get('bot_id')==BOT and marker.get('message_id')==inbox.get('input_message_id')
      and marker.get('bridge_request_text')==QUESTION)
def main():
    p=get(TRIAL+'telegram_policy') or {}
    if not p.get('enabled') or p.get('question')!=QUESTION or p.get('chat_id')!=CHAT or p.get('owner_id')!=OWNER:raise RuntimeError('Trial policy invalid')
    state=get(TRIAL+'session') or {};sid=state.get('session_id')
    if not sid or (get(TRIAL+'result') or {}).get('status')!='verified':raise RuntimeError('Work continuity not verified')
    if get(TRIAL+'telegram_result'):raise RuntimeError('One-shot trial already used')
    print('Cloud owner-question worker ready',flush=True)
    for attempt in range(120):
        if datetime.now(timezone.utc)>=datetime.fromisoformat(p['expires_at']):break
        bridge=get(ROOT+'policy') or {}
        if not bridge.get('enabled') or bridge.get('thread_id')!=THREAD or bridge.get('chat_id')!=CHAT or bridge.get('bot_id')!=BOT:raise RuntimeError('Bridge scope invalid')
        rows=api('GET','telegram_api_cache',{'cache_key':'like.'+ROOT+'inbox:*','payload->>status':'eq.queued','payload->>request_text':'eq.'+QUESTION,'order':'updated_at.asc','limit':'1','select':'cache_key,payload'})
        if not rows:time.sleep(5);continue
        key=rows[0]['cache_key'];inbox=rows[0]['payload'];jid=inbox['job_id']
        jobs=api('GET','business_agent_jobs',{'id':'eq.'+str(jid),'chat_id':'eq.'+str(CHAT),'select':'id,chat_id,sender_id,request_text,tool_trace'})
        if len(jobs)!=1 or not valid(inbox,jobs[0]):raise RuntimeError('Original question verification failed')
        if get(ROOT+'outbox:'+str(jid)):raise RuntimeError('Existing answer; no duplicate')
        claimed=inbox|{'status':'cloud_processing','cloud_trial':True}
        changed=api('PATCH','telegram_api_cache',{'cache_key':'eq.'+key,'payload->>status':'eq.queued'}, {'payload':claimed,'updated_at':stamp()})
        if not changed:raise RuntimeError('Claim lost')
        text=[];completed=False
        client=OpenAI(max_retries=0,timeout=100)
        with client.beta.agents.sessions.events.stream(sid) as events:
            client.beta.agents.sessions.events.create(sid,idempotency_key='veschi-live-trial-'+str(jid),events=[{'type':'agent.session.input.message','input':[{'role':'user','content':[{'type':'input_text','text':'Владелец прислал проверенный вопрос из рабочей группы: '+QUESTION+'. Ответь естественно по-русски, без JSON и техдиагностики, до 600 знаков, по известным договорённостям на 3 ноября 2026. Не обещай действий. В конце отдельной строкой: «Тестовый ответ облачной сессии». '}]}]}])
            for event in events:
                if event.type.endswith('output_text.delta'):text.append(event.to_dict().get('delta',''))
                if event.type=='agent.session.turn.completed' and event.turn.subagent_id is None:completed=True;break
                if event.type in ('error','agent.session.failed','agent.session.turn.failed','agent.session.turn.cancelled'):raise RuntimeError('Cloud turn failed; do not retry')
        answer=''.join(text).strip()
        if not completed or not 0<len(answer)<=1000:raise RuntimeError('No completed bounded answer')
        if '4 ноября' not in answer and '04.11' not in answer:raise RuntimeError('Expected review date absent')
        if get(ROOT+'outbox:'+str(jid)):raise RuntimeError('Answer appeared during model call')
        out={'status':'ready','job_id':jid,'chat_id':CHAT,'input_message_id':inbox['input_message_id'],
             'thread_id':THREAD,'answer':answer,'created_at':stamp(),'source_channel':'codex_cloud_trial',
             'wb_action_permission':False,'cloud_session_id':sid,'cloud_trial':True}
        once(ROOT+'outbox:'+str(jid),out)
        api('PATCH','telegram_api_cache',{'cache_key':'eq.'+key,'payload->>status':'eq.cloud_processing'},
            {'payload':claimed|{'status':'answered'},'updated_at':stamp()})
        if (get(key) or {}).get('status')!='answered':raise RuntimeError('Inbox readback mismatch')
        once(TRIAL+'telegram_result',{'status':'ready','job_id':jid,'answer':answer,'created_at':stamp(),
            'source_channel':'codex_cloud_trial','run_id':os.environ['GITHUB_RUN_ID'],'wb_writes':0,
            'direct_telegram_sends':0,'delivery_requires_receipts':True})
        print(json.dumps({'cloud_answer_ready':True,'job_id':jid}),flush=True);return
    print('No owner test question before expiry',flush=True)
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'error_type':type(exc).__name__}),flush=True);raise SystemExit(1)
