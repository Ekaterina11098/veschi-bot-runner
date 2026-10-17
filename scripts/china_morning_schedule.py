"""Select one current Moscow-day morning pair; delivery identities live in PairWorker."""
import json,os
from datetime import datetime
from zoneinfo import ZoneInfo

SOURCE='b90b5e83efd7c691d6a3d24b1d17b35c0e7da99c'

def select(event,requested,value,day):
    automatic=event in ('schedule','workflow_dispatch')
    action=('run' if event=='schedule' else requested or 'verify') if automatic else value.get('action')
    allowed=(event in ('schedule','workflow_dispatch','push') and value.get('source_commit')==SOURCE
             and action in ('run','verify') and (automatic or (value.get('report_date')==day
             and value.get('mode')=='morning' and isinstance(value.get('nonce'),str) and len(value['nonce'])>=8)))
    return {'allowed':allowed,'action':action,'report_date':day,'mode':'morning'}

def main():
    with open('china-price-morning-request.json',encoding='utf-8') as f:value=json.load(f)
    result=select(os.environ.get('EVENT_NAME'),os.environ.get('REQUESTED_ACTION'),value,datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat())
    with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:
        for key in ('allowed','action','report_date'):f.write(key+'='+str(result[key]).lower()+'\n')
    print(json.dumps(result))

if __name__=='__main__':main()
