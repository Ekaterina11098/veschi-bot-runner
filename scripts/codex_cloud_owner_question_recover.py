import os,json
from datetime import datetime,timezone,timedelta
from urllib.request import Request,urlopen
from codex_cloud_owner_question_trial import api,get,valid,stamp,ROOT,TRIAL,THREAD,CHAT,QUESTION
def once(key,value):
    api('POST','telegram_api_cache',body={'cache_key':key,'payload':value,'updated_at':stamp(),'expires_at':(datetime.now(timezone.utc)+timedelta(days=30)).isoformat()})
    if get(key)!=value:raise RuntimeError('Readback mismatch')
def read_openai(path):
    sid=(get(TRIAL+'session') or {})['session_id']
    req=Request('https://api.openai.com/v1/agents/sessions/'+sid+path,headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'],'OpenAI-Beta':'agents=v1'})
    with urlopen(req,timeout=30) as r:return json.load(r)
jid=230;key=ROOT+'inbox:'+str(jid)
inbox=get(key);jobs=api('GET','business_agent_jobs',{'id':'eq.'+str(jid),'chat_id':'eq.'+str(CHAT),'select':'id,chat_id,sender_id,request_text,tool_trace'})
assert len(jobs)==1 and valid(inbox,jobs[0]) and inbox['status']=='cloud_processing'
assert not get(ROOT+'outbox:'+str(jid)) and not get(TRIAL+'telegram_result')
turns=read_openai('/turns?order=desc&limit=5')['data']
turn=next(t for t in turns if t.get('subagent_id') is None)
assert turn['status']=='completed' and turn['created_at']>=int(datetime.fromisoformat(inbox['created_at']).timestamp())-5
items=read_openai('/items?order=asc&limit=100')
assert not items.get('has_more')
bound=[i for i in items['data'] if i.get('turn_id')==turn['id']]
assert any(i.get('role')=='user' and QUESTION in json.dumps(i,ensure_ascii=False) for i in bound)
messages=[i for i in bound if i.get('role')=='assistant' and i.get('status')=='completed']
answer=''.join(c.get('text','') for i in messages for c in i.get('content',[]) if c.get('type')=='output_text').strip()
assert 0<len(answer)<=1000 and ('4 ноября' in answer or '04.11' in answer)
out={'status':'ready','job_id':jid,'chat_id':CHAT,'input_message_id':inbox['input_message_id'],'thread_id':THREAD,'answer':answer,
 'created_at':stamp(),'source_channel':'codex_cloud_trial','wb_action_permission':False,'cloud_trial':True,'cloud_turn_id':turn['id']}
once(ROOT+'outbox:'+str(jid),out)
api('PATCH','telegram_api_cache',{'cache_key':'eq.'+key,'payload->>status':'eq.cloud_processing'},{'payload':inbox|{'status':'answered'},'updated_at':stamp()})
assert get(key)['status']=='answered'
once(TRIAL+'telegram_result',{'status':'ready','job_id':jid,'answer':answer,'created_at':stamp(),'source_channel':'codex_cloud_trial',
 'run_id':os.environ['GITHUB_RUN_ID'],'recovered_completed_turn':turn['id'],'model_resubmissions':0,'usage':turn.get('usage'),'wb_writes':0,'direct_telegram_sends':0})
print(json.dumps({'recovered_completed_cloud_turn':True,'job_id':jid,'outbox_readback':True}))
