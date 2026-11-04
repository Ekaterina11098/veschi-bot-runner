"""Continue only the explicitly rejected429 price upload; never repeat advertising writes."""
import os,time,json,copy
import ooo_urgent_execute_20261104 as u
w=u.w
ROOT=u.ROOT
CHILD=ROOT+':price_continuation'
old=w.get(ROOT+':execution')
if not old or old.get('steps',{}).get('price_143',{}).get('status')!='rejected_429' or any(old['steps'].get(k,{}).get('status')!='accepted'for k in ['add_594','bids_594_59']):raise SystemExit('No unaccepted price-only continuation')
w.KEY=CHILD
if not w.claim({'status':'claimed','run_id':os.environ['GITHUB_RUN_ID'],'started_at':w.stamp()}):raise SystemExit('Price continuation already claimed')
w.KEY=ROOT+':execution';w.state=old
price_req=u.price_req
try:
 u.scope()
 w.state.setdefault('rejected_price_history',[]).append(copy.deepcopy(w.state['steps']['price_143']))
 del w.state['steps']['price_143']
 w.state.pop('error',None);w.state.update(status='waiting_price_quota',continuation_run_id=os.environ['GITHUB_RUN_ID']);w.save()
 upload=price_req('/api/v2/upload/task',{'data':[{'nmID':851316021,'price':13000,'discount':46}]},'price_143')
 if type(upload.get('id'))is not int or upload['id']<=0:raise RuntimeError('Missing task ID; no replay')
 w.state.update(status='all_writes_accepted',upload_id=upload['id'],all_writes_accepted_at=w.stamp());w.save()
 before={int(k):v for k,v in w.state['before'].items()}
 for _ in range(45):
  task=price_req('/api/v2/history/tasks?uploadID='+str(upload['id']))
  if task.get('uploadID')!=upload['id']:raise RuntimeError('Price task identity mismatch')
  w.state['price_task']=task;w.save()
  if task.get('status')in[3,4,5,6]:break
  time.sleep(15)
 else:raise RuntimeError('Price processing pending; do not repeat upload')
 if task['status']not in[3,5]:raise RuntimeError('Price task completed with failure')
 details=price_req('/api/v2/history/goods/task?uploadID='+str(upload['id'])+'&limit=1000&offset=0')
 items=[g for g in details.get('historyGoods',[])if g.get('nmID')==851316021]
 if details.get('uploadID')!=upload['id']or len(items)!=1 or items[0].get('errorText'):raise RuntimeError('Price details not verified')
 w.state.update(price_details=details,status='price_task_processed');w.save()
 after=w.configs([41516310,40385586])
 for cid in before:
  for k in['id','status','currency','bid_type','settings','restrictions']:
   if after[cid].get(k)!=before[cid].get(k):raise RuntimeError('Unapproved configuration difference')
  expected=w.member_ids(before[cid])|({1124312584}if cid==41516310 else set())
  if w.member_ids(after[cid])!=expected:raise RuntimeError('Membership readback mismatch')
  for b in before[cid]['nm_settings']:
   n=next(n for n in after[cid]['nm_settings']if n['nm_id']==b['nm_id']);expected=copy.deepcopy(b)
   if cid==40385586 and b['nm_id']==1124312594:expected['bids_kopecks']['recommendations']=360
   if n!=expected:raise RuntimeError('Unapproved SKU difference')
 if next(n for n in after[41516310]['nm_settings']if n['nm_id']==1124312584)['bids_kopecks']['search']!=325:raise RuntimeError('594 bid readback mismatch')
 w.state.update(status='advertising_verified',after=after,advertising_verified_at=w.stamp());w.save()
 fresh=price_req('/api/v2/list/goods/filter?limit=1000&offset=0&filterNmID=851316021').get('listGoods',[])
 if len(fresh)!=1:raise RuntimeError('143 exact price row missing')
 g=fresh[0]
 if g['nmID']!=851316021 or g['vendorCode']!='143-ReginaBag-black'or g['currencyIsoCode4217']!='RUB'or g['discount']!=46 or g['clubDiscount']!=0 or any(z['price']!=13000 or z['discountedPrice']!=7020 for z in g['sizes']):raise RuntimeError('Final price readback mismatch')
 w.state.update(status='verified',price_after=g,verified_at=w.stamp(),first_full_test_day='2026-11-05',advertising_test_full_days=2,price_test_full_days=3);w.save()
except Exception as e:
 w.state.update(status='attention',error=str(e)if isinstance(e,(RuntimeError,ValueError,PermissionError,KeyError))else type(e).__name__);w.save()
w.put(CHILD,{'status':'finished','parent_status':w.state['status'],'run_id':os.environ['GITHUB_RUN_ID'],'finished_at':w.stamp()})
print(json.dumps({'status':w.state['status']}))
