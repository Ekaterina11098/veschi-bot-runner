"""Deliver a scoped read-only correction without replaying the original job or plan."""
import argparse,hashlib,json,os
from china_free_diagnostics import CHAT,intent,handle
ROOT='china_agent:free_repair10:v1:'

def repair(w,jid):
    from china_free_ads import confirmation_text
    from china_table_png import delivery_parts
    from conversion_watches import split_message
    cfg=w.config()
    if cfg.get('chat_id')!=CHAT or cfg.get('bot_id')!=8780468043:raise PermissionError('Bot scope changed')
    rows=w.db('GET','business_agent_jobs',params={'id':'eq.'+str(jid),'agent_id':'eq.china','chat_id':'eq.'+str(CHAT),'select':'*','limit':1})or[]
    if len(rows)!=1:raise ValueError('Original question missing')
    original=rows[0];m=next((x for x in original.get('tool_trace',[])if x.get('name')=='china_saved_question'),{})
    if original.get('sender_id')not in(5122667182,307200273) or m.get('bot_id')!=8780468043 or type(m.get('message_id'))is not int:
        raise PermissionError('Original question marker mismatch')
    question=confirmation_text(original)
    if intent(question)not in('drr','minimums','coverage'):raise ValueError('Not a supported read-only diagnostic')
    key=ROOT+str(jid);saved=w.get(key)
    if saved and saved.get('status')=='delivered':return {'job_id':jid,'status':'already_delivered','message_ids':saved['message_ids']}
    if not saved:
        answer=handle(w,dict(original,request_text=question))
        audit=w.get('china_agent:free_diagnostic:v1:'+str(jid))or{}
        if audit.get('status')!='answered':raise RuntimeError('Read-only diagnostic failed; correction not sent')
        saved=dict(status='prepared',job_id=jid,chat_id=CHAT,input_message_id=m['message_id'],answer=answer,
                   question_sha256=hashlib.sha256(question.encode()).hexdigest(),paid_model_calls=0,wb_writes=0)
        if not w.save(key,saved,insert=True):saved=w.get(key)
    if not saved or saved.get('job_id')!=jid or saved.get('chat_id')!=CHAT or saved.get('input_message_id')!=m['message_id'] or saved.get('question_sha256')!=hashlib.sha256(question.encode()).hexdigest():
        raise PermissionError('Frozen correction scope changed')
    artifact_job=dict(original,id='repair-free10-'+str(jid))
    w.active_question_id=artifact_job['id'];w.reply_id=m['message_id']
    parts=delivery_parts(w,artifact_job,saved['answer'],split_message);message_ids=[]
    for i,part in enumerate(parts):
        receipt='free-repair10:'+str(jid)+':'+str(i)
        outcome=w.send_once(receipt,CHAT,part)
        proof=w.get('china_agent:conversion_watch_delivery:v1:'+receipt)or{}
        if outcome!='sent' or proof.get('status')!='sent' or proof.get('chat_id')!=CHAT or type(proof.get('message_id'))is not int:
            raise RuntimeError('Correction delivery unresolved; no blind resend')
        message_ids.append(proof['message_id'])
    w.save(key,dict(saved,status='delivered',message_ids=message_ids,delivered_at=w.now.isoformat()))
    return dict(job_id=jid,status='delivered',message_ids=message_ids,paid_model_calls=0,wb_writes=0)

def main():
    p=argparse.ArgumentParser();p.add_argument('--job-id',required=True,type=int,action='append');args=p.parse_args()
    if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':
        raise PermissionError('Public runner main only')
    from conversion_watches import runtime,saved_network_guard
    w=runtime()
    for jid in args.job_id:
        with saved_network_guard():result=repair(w,jid)
        print(json.dumps(result))
if __name__=='__main__':main()
