"""Owner-requested China search analytics read probe. No WB mutations."""
import os,json,time,base64
from datetime import datetime,timezone
import requests
from china_price_apply import IO
io=IO();key='china_agent:search_api_probe:2026-10-21:v1'
if io.get(key):print('already_collected');raise SystemExit()
token=io.token
card=io.prices(['1473243898'])['1473243898']
if card.get('vendorCode')!='119-NoelBag-darkblack' or card.get('currencyIsoCode4217')!='CNY':raise RuntimeError('Seller scope')
state={'cabinet':'token_3','nm_id':1473243898,'started_at':datetime.now(timezone.utc).isoformat(),'observations':[],'wb_writes':0,'telegram_calls':0}
period={'start':'2026-10-14','end':'2026-10-20'}
queries=[
('/api/v2/search-report/table/details',{'currentPeriod':period,'pastPeriod':{'start':'2026-10-07','end':'2026-10-13'},'nmIds':[1473243898],'includeSubstitutedSKUs':True,'includeSearchTexts':True,'orderBy':{'field':'openCard','mode':'desc'},'limit':10,'offset':0}),
('/api/v2/search-report/product/search-texts',{'currentPeriod':period,'pastPeriod':{'start':'2026-10-07','end':'2026-10-13'},'nmIds':[1473243898],'topOrderBy':'openCard','includeSubstitutedSKUs':True,'includeSearchTexts':True,'orderBy':{'field':'openCard','mode':'desc'},'limit':30})]
for i,(path,body) in enumerate(queries):
 if i:time.sleep(21)
 r=requests.post('https://seller-analytics-api.wildberries.ru'+path,headers={'Authorization':token},json=body,timeout=45,allow_redirects=False)
 try:data=r.json()
 except ValueError:data={'body_not_json':True}
 state['observations'].append({'path':path,'request':body,'status_code':r.status_code,'data':data,'retry_after':r.headers.get('Retry-After')})
 if r.status_code in (401,402,403,429):break
state['completed_at']=datetime.now(timezone.utc).isoformat();state['status']='complete'
io.create(key,state)
print(json.dumps({'status':'complete','http_codes':[x['status_code'] for x in state['observations']],'wb_writes':0,'telegram_calls':0}))
