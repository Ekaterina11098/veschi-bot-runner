"""One read per WB service; evidence stays private. No marketplace or Telegram writes."""
import os,json,base64
from datetime import datetime,timezone
import requests
from conversion_watches import runtime

def identity(token):
 try:return json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='))
 except Exception:return {}

def main():
 w=runtime();out={'observed_at':datetime.now(timezone.utc).isoformat(),'cabinet':'token_3','wb_writes':0,'telegram_sends':0,'sources':{}}
 wb=os.environ['WB_TOKEN_3'];finance=os.environ.get('WB_FINANCE_TOKEN_3') or wb
 if identity(finance).get('sid')!=identity(wb).get('sid'):raise ValueError('Finance seller identity mismatch')
 for name,url,body,token in [
  ('funnel','https://seller-analytics-api.wildberries.ru/api/analytics/v3/sales-funnel/products',{'selectedPeriod':{'start':'2026-10-22','end':'2026-10-22'},'pastPeriod':{'start':'2026-10-21','end':'2026-10-21'},'nmIds':[],'brandNames':[],'subjectIds':[],'tagIds':[],'skipDeletedNm':False,'orderBy':{'field':'openCard','mode':'desc'},'limit':1000,'offset':0},wb),
  ('finance','https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed',{'dateFrom':'2026-09-23','dateTo':'2026-10-22','period':'daily','limit':100000,'rrdId':0},finance)]:
  key='china_agent:wb_evidence_probe:v1:'+name+':2026-10-23'
  old=w.get(key)
  if old:out['sources'][name]={'status':old['status'],'cached':True};continue
  r=requests.post(url,headers={'Authorization':token},json=body,timeout=90,allow_redirects=False)
  value={'source':url,'request':body,'status':r.status_code,'observed_at':out['observed_at'],'cabinet':'token_3','retry_after':r.headers.get('Retry-After')}
  try:value['data']=r.json()
  except ValueError:value['response_excerpt']=r.text[:800]
  w.save(key,value);out['sources'][name]={'status':r.status_code,'cached':False}
 w.save('china_agent:wb_evidence_probe:v1:summary',out)
 print(json.dumps(out))

if __name__=='__main__':
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner':raise SystemExit('Public runner only')
 main()

