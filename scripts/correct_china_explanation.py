"""Correct exactly our proven invalid answer in place; no new message or source reads."""
import os,sys,json
from datetime import datetime,timezone
sys.path.insert(0,'source');sys.path.insert(0,'scripts')
from conversion_watches import runtime,saved_network_guard,RECEIPTS
w=runtime();cfg=w.config();assert cfg['chat_id']==-1004342917488 and cfg['bot_id']==8780468043
rows=w.db('GET','business_agent_jobs',params={'id':'eq.45','agent_id':'eq.china','chat_id':'eq.-1004342917488','select':'*'})
assert len(rows)==1
j=rows[0];assert j['status']=='done' and j['request_text']=='А почему снизилась конверсия?'
key=RECEIPTS+'question:45:0';receipt=w.get(key)
assert receipt['status']=='sent' and receipt['message_id']==7 and receipt['chat_id']==cfg['chat_id']
evidence_key='china_agent:answer_correction:v1:45'
existing=w.get(evidence_key)
if existing:
 print(json.dumps({'status':existing['status'],'telegram_new_sends':0}));sys.exit(0 if existing['status']=='corrected' else 1)
w.collect=None
parents=w.db('GET','business_agent_jobs',params={'id':'eq.44','agent_id':'eq.china','chat_id':'eq.'+str(cfg['chat_id']),'sender_id':'eq.'+str(j['sender_id']),'status':'eq.done','select':'*'})
assert len(parents)==1 and j['tool_trace'][0]['parent_job_id']==44 and j['tool_trace'][0]['reply_message_id']==5
with saved_network_guard():answer,trace=w.saved_question(j,parents)
assert trace and trace[0]['name']=='saved_conversion_explanation' and trace[0]['arguments']['nm_id']=='1473243825'
assert '2026-10-12–2026-10-16' in answer and '298' not in answer
evidence={'status':'prepared','job_id':45,'message_id':7,'chat_id':cfg['chat_id'],'previous_answer':j['answer'],'corrected_answer':answer,'trace':trace,'source_calls':0,'model_calls':0,'telegram_new_sends':0}
if not w.save(evidence_key,evidence,insert=True):raise RuntimeError('Correction already claimed')
evidence['status']='editing';w.save(evidence_key,evidence)
import requests
try:
 result=requests.post('https://api.telegram.org/bot'+os.environ['CHINA_TELEGRAM_BOT_TOKEN'].strip()+'/editMessageText',json={'chat_id':cfg['chat_id'],'message_id':7,'text':answer,'disable_web_page_preview':True},timeout=35).json()
except Exception:
 evidence['status']='uncertain';w.save(evidence_key,evidence);raise RuntimeError('Correction uncertain; do not resend') from None
if not result.get('ok'):
 evidence['status']='rejected';w.save(evidence_key,evidence);raise RuntimeError('Correction rejected')
message=result['result'];assert message['message_id']==7 and message['chat']['id']==cfg['chat_id']
patched=w.db('PATCH','business_agent_jobs',params={'id':'eq.45','agent_id':'eq.china','status':'eq.done'},body={'answer':answer,'tool_trace':[j['tool_trace'][0]]+trace+[{'name':'china_answer_corrected','evidence_cache_key':evidence_key,'reason':'Replace unsupported causal guesses with exact parent daily arithmetic and explicit evidence limits'}]},prefer='return=representation')
assert len(patched)==1 and patched[0]['answer']==answer
receipt.update(text=answer,correction_evidence=evidence_key);w.save(key,receipt)
evidence.update(status='corrected',confirmed_at=datetime.now(timezone.utc).isoformat());w.save(evidence_key,evidence)
print(json.dumps({'status':'corrected','job_id':45,'message_id':7,'exact_nm_verified':True,'model_calls':0,'source_calls':0,'telegram_new_sends':0,'telegram_edits':1,'wb_writes':0}))
