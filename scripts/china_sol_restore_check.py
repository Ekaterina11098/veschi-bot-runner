"""One owner-authorized real Sol inference; no Telegram or WB transport."""
import json
from datetime import datetime,timezone
from china_codex_cloud import Worker,ROOT,CLOUD,CHAT,INSTRUCTIONS,envelope
from bounded_sol_dialog import compact_message
w=Worker()
key='china_agent:sol_restore_check:2026-11-08:v1'
old=w.db.get(key)
if old:
 print(json.dumps({'status':old['status'],'already_checked':True}));raise SystemExit()
inbox=w.db.get(ROOT+'inbox:270')
if not inbox or inbox.get('chat_id')!=CHAT:raise ValueError('Original Pavel request missing')
ctx=w.context(inbox)
review=w.db.get('china_agent:new_ad_candidate_review:v1:268')or{}
ctx['candidate_review']=review.get('review')
message=compact_message({'runtime_scope':{'chat_id':CHAT,'sender_id':307200273,'wb_action_permission':False,'verification_only':True},'dated_work_context':ctx,'untrusted_telegram_question':inbox['request_text']})
sid=w.bootstrap()['session_id']
answer=w.generate(sid,message,'owner-sol-restoration-check-20261108-pavel270-v1')
parsed=envelope(answer)
value=dict(status='model_completed',source_job_id=270,source_input_message_id=779,model='gpt-6.1-sol',response=parsed,verified_at=datetime.now(timezone.utc).isoformat(),telegram_sent=False,wb_writes=0)
w.db.once(key,value)
print(json.dumps({'status':value['status'],'response_kind':parsed['kind'],'wb_writes':0,'telegram_sent':False}))
