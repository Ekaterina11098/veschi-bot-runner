"""Skip fallback collection outside agreed report windows or after real delivery."""
import argparse,json,os,urllib.parse,urllib.request
from datetime import date,datetime
from zoneinfo import ZoneInfo

def in_window(now,mode):
    value=now.hour*60+now.minute
    low=630 if mode=='morning' else 900
    return low<=value<low+46

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['morning','intraday'],required=True);a=p.parse_args()
    now=datetime.now(ZoneInfo('Europe/Moscow'));allowed=True;reason='primary_schedule'
    if os.environ.get('EVENT_NAME')=='workflow_call':
        allowed=in_window(now,a.mode);reason='fallback_due_window' if allowed else 'outside_agreed_window'
    preview=False
    if os.environ.get('EVENT_NAME')=='push':
        try:
            with open('china-price-'+a.mode+'-request.json',encoding='utf8') as f:request=json.load(f)
            preview=request.get('action')=='verify' and request.get('report_date')==str(now.date()) and request.get('mode')==a.mode
        except (OSError,ValueError):pass
    if allowed and not preview:
        update=-(9800000000 if a.mode=='morning' else 9600000000)-(now.date()-date(2020,1,1)).days
        q=urllib.parse.urlencode(dict(agent_id='eq.china',update_id='eq.'+str(update),select='id,status,tool_trace',limit=2))
        secret=os.environ['SUPABASE_SECRET_KEY']
        req=urllib.request.Request(os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/business_agent_jobs?'+q,headers={'apikey':secret,'Authorization':'Bearer '+secret})
        with urllib.request.urlopen(req,timeout=30) as response:jobs=json.load(response)
        if len(jobs)>1:raise RuntimeError('Price report identity ambiguous')
        if jobs and jobs[0]['status']=='done':
            delivered=any(e.get('name')=='china_report_delivery' and e.get('sent_parts') and e.get('message_ids') for e in jobs[0].get('tool_trace',[]))
            if not delivered:raise RuntimeError('Completed price job lacks visible receipt')
            allowed=False;reason='already_delivered'
    with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('allowed='+str(allowed).lower()+'\n')
    print(json.dumps(dict(mode=a.mode,allowed=allowed,reason=reason)))
if __name__=='__main__':main()

