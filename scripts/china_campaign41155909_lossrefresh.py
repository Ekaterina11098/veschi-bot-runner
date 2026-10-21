"""Owner-requested original China finance audit. Read-only finance POST only."""
import os,sys,json,time,base64
from datetime import timedelta
from decimal import Decimal
from urllib.parse import quote
import requests
sys.path.insert(0,'scripts')
from china_price_apply import IO,now,day
KEY='china_agent:commission_return_audit:2026-10-21:v1'
FIELDS=('rrdId','rrDate','nmId','vendorCode','docTypeName','sellerOperName','quantity','retailPrice','retailPriceWithDisc','retailAmount','forPay','deliveryService','deliveryAmount','returnAmount','bonusTypeName','currency','currencyName','acquiringFee','acquiringPercent','commissionPercent','ppvzSalesCommission','ppvzReward','kvwBase','kvw','deduction','paidStorage','paidAcceptance','penalty','rebillLogisticCost','additionalPayment','cashbackAmount','cashbackCommissionChange','paymentSchedule','cashbackDiscount','dateFrom','dateTo','reportId','saleDt','orderDt')
def finance_main():
 if day()!='2026-10-21':raise RuntimeError('Expired audit')
 io=IO()
 if io.get(KEY):print('Existing audit preserved');return
 token=os.getenv('WB_FINANCE_TOKEN_3','').strip()
 result=dict(cabinet='token_3',period_from='2026-09-21',period_to='2026-10-20',observed_at=now().isoformat(),wb_writes=0,marketplace_mutations=0,telegram_calls=0,pages=[],purpose='original_CNY_commission_and_return_operations_missing_from_MPStats')
 if not token:
  result.update(status='unavailable',reason='Dedicated China finance credential unavailable');io.create(KEY,result);print(json.dumps(result));return
 claims=json.loads(base64.urlsafe_b64decode(token.removeprefix('Bearer ').split('.')[1]+'==='))
 identities=io.db('analytics_snapshots?cabinet=eq.token_3&source=eq.seller_identity&status=eq.complete&select=payload&order=id.desc&limit=1')
 if len(identities)!=1 or claims.get('sid')!=identities[0]['payload'].get('sid') or not(int(claims.get('s',0))&(1<<13)):raise RuntimeError('China finance identity/scope unverified')
 result.update(status='reading',identity_verified=True)
 if not io.create(KEY,result):raise RuntimeError('Concurrent audit')
 url='https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed'
 cursor=0;seen=set()
 for page in range(3):
  if page:time.sleep(62)
  r=requests.post(url,headers={'Authorization':token},json=dict(dateFrom='2026-09-21',dateTo='2026-10-20',period='weekly',limit=100000,rrdId=cursor),timeout=(15,120))
  if r.status_code==204:
   result.update(status='complete',terminal_204=True,row_count=len(seen));io.put(KEY,result);print(json.dumps(dict(status='complete',rows=len(seen),pages=len(result['pages']),wb_writes=0)));return
  if not r.ok:
   result.update(status='unavailable',http_status=r.status_code);io.put(KEY,result);print(json.dumps(dict(status=result['status'],http_status=r.status_code,wb_writes=0)));return
  body=r.json();rows=body if isinstance(body,list) else body.get('data',body.get('rows')) if isinstance(body,dict) else None
  if not isinstance(rows,list) or not rows:raise RuntimeError('Unexpected Finance response')
  clean=[]
  for row in rows:
   identity=int(row.get('rrdId',row.get('rrd_id',0)))
   if identity<=cursor or identity in seen:raise RuntimeError('Cursor duplicate/out-of-scope')
   currency=str(row.get('currency',row.get('currencyName',''))).lower()
   if currency not in ('cny','юань','юани'):raise RuntimeError('Unexpected China settlement currency')
   seen.add(identity);clean.append({k:row[k] for k in FIELDS if k in row})
  cursor=max(seen)
  pkey=KEY+':page:'+str(page)
  if not io.create(pkey,dict(rows=clean,cabinet='token_3',scope='weekly 2026-09-21 through 2026-10-20')):raise RuntimeError('Duplicate page audit')
  result['pages'].append(dict(cache_key=pkey,rows=len(clean),last_rrd_id=cursor))
  result.update(row_count=len(seen),cursor=cursor);io.put(KEY,result)
 result['status']='bounded_incomplete';io.put(KEY,result);print(json.dumps(dict(status=result['status'],rows=len(seen),wb_writes=0)))


from analytics.mpstats_probe import discover,unpack_tool,sanitize,ProbeError
io=IO()
delete_key='china_agent:loss_report:2026-10-21:delete87:v1'
existing=io.get(delete_key)
if not existing:
 audit=dict(status='sending',chat_id=-1004342917488,message_id=87,requested_by='owner',created_at=now().isoformat())
 if not io.create(delete_key,audit):raise RuntimeError('Concurrent deletion')
 result=io.tg('deleteMessage',dict(chat_id=-1004342917488,message_id=87))
 if result is not True:raise RuntimeError('Deletion not confirmed')
 audit.update(status='deleted',result=True,completed_at=now().isoformat());io.put(delete_key,audit)
 original=io.get('china_agent:loss_report:2026-10-21:v1')
 original['deleted_at']=audit['completed_at'];original['deletion_audit']=delete_key;io.put('china_agent:loss_report:2026-10-21:v1',original)
finance_main()
key='china_agent:economics_audit:2026-10-21:v1'
def reader(call,checks,seen):
 def tool(name,args):return sanitize(unpack_tool(call('tools/call',dict(name=name,arguments=args))))
 cabinets=checks['lk_wb_cabinets'];selected=[x['id'] for x in cabinets if x.get('selected')]
 if len(selected)>1 or len([x for x in cabinets if x.get('id')==10026946 and x.get('valid')])!=1:raise ProbeError('China identity mismatch')
 out=dict(cabinet='token_3',observed_at=now().isoformat(),reports={},wb_writes=0)
 try:
  tool('lk_wb_cabinets',dict(action='select',id=10026946))
  if [x['id'] for x in tool('lk_wb_cabinets',dict(action='list')) if x.get('selected')]!=[10026946]:raise ProbeError('Scope mismatch')
  for name in ['lk_wb_dashboard_table','lk_wb_dashboard_expenses']:
   args=dict(period_type='30days',date_from='2026-09-21',date_to='2026-10-20')
   out['reports'][name]=dict(status='received',arguments=args,data=tool(name,args))
 finally:tool('lk_wb_cabinets',dict(action='select',id=selected[0]) if selected else dict(action='reset'))
 return out
if not io.get(key):
 r=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=reader)
 io.create(key,dict(status=r['status'],extra_reads=r.get('extra_reads'),detail=r.get('detail'),wb_writes=0))
prices=[];offset=0
while True:
 data=io.wb('/api/v2/list/goods/filter?limit=1000&offset='+str(offset))
 rows=data.get('listGoods',[]);prices+=rows
 if len(rows)<1000:break
 offset+=len(rows)
 if offset>5000:raise RuntimeError('Price pagination exceeded')
audit=dict(cabinet='token_3',rows=prices,observed_at=now().isoformat(),wb_writes=0)
io.create('china_agent:loss_price_snapshot:2026-10-21:v1',audit)
print(json.dumps(dict(status='collected',prices=len(prices),wb_writes=0,deleted_message=87)))
