"""Continue one exact no-paid dialogue job; no historic queue replay."""
import argparse,json,os

def run(io,job_id):
    from china_new_ad_reports import process_requests
    from china_loss_control import APPROVAL,PLAN
    from china_new_ads import process_and_deliver,validate_plan
    rows=io.db('business_agent_jobs?id=eq.'+str(job_id)+'&agent_id=eq.china&chat_id=eq.-1004342917488&select=id,status')
    if len(rows)!=1 or rows[0]['status']!='done':return {'status':'waiting_dialogue','job_id':job_id}
    process_requests(io,job_id=job_id)
    approval=io.get(APPROVAL+str(job_id))
    if approval and approval.get('status')=='approved' and approval.get('job_id')==job_id:
        plan=io.get(PLAN+approval['plan_id'])
        if not plan or plan.get('execution_kind')!='ad_create_campaigns':
            return {'status':'other_plan_not_executed','job_id':job_id}
        validate_plan(plan)
        process_and_deliver(io,approval,plan)
    return {'status':'processed_exact_job','job_id':job_id,'paid_model_calls':0}

def main():
    p=argparse.ArgumentParser();p.add_argument('--job-id',required=True,type=int);args=p.parse_args()
    if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':
        raise PermissionError('Public runner main only')
    from china_loss_execute import IO
    print(json.dumps(run(IO(),args.job_id)))
if __name__=='__main__':main()
