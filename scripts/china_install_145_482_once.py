"""One-time owner instruction in Codex: exact China 145/482 initial prices."""
import json,time
from decimal import Decimal
from china_price_apply import IO,now
io=IO()
key='china_agent:manual_price_install:2026-10-19:145-482:v1'
targets=[dict(article='145-FlorenceBag-black',nm_id='1900197978',price=676,discount=50,net=338),dict(article='482-RiginaBag-red',nm_id='1900202932',price=754,discount=50,net=377)]
io.capability()
e=io.get(key)
if e and e['status'] in ['submitting','uncertain']:
    raise RuntimeError('Uncertain prior submission; no blind replay')
if not e:
    before=io.prices([x['nm_id'] for x in targets])
    for t in targets:
        p=before[t['nm_id']]
        if p['vendorCode']!=t['article'] or p.get('currencyIsoCode4217')!='CNY' or p.get('editableSizePrice') is not False:
            raise RuntimeError('Exact card identity/currency mismatch')
        if not p.get('sizes') or p['discount']!=0 or any(Decimal(str(s['price']))!=0 for s in p['sizes']):
            raise RuntimeError('Initial price changed since approval; do not overwrite')
        lock=io.get('china_agent:price_write_lock:v1:'+t['nm_id'])
        if lock and lock.get('status') in ['submitting','submitted','uncertain']:
            raise RuntimeError('Unresolved price write exists')
    e=dict(status='prepared',authorized_by='Explicit owner Codex request 2026-10-19: base145=676/base482=754,discount50both',targets=targets,before=before,created_at=now().isoformat())
    if not io.create(key,e):raise RuntimeError('Concurrent install')
if e['status']=='done':
    fresh=io.prices([t['nm_id'] for t in targets]);print(json.dumps(dict(status='already_installed',prices=fresh),ensure_ascii=False));raise SystemExit()
if e['status']=='prepared':
    for t in targets:
        lock='china_agent:price_write_lock:v1:'+t['nm_id']
        payload=dict(execution=key,status='submitting',created_at=now().isoformat(),target=t)
        if io.get(lock):io.put(lock,payload)
        elif not io.create(lock,payload):raise RuntimeError('Concurrent item claim')
    e['status']='submitting';e['request']=dict(data=[dict(nmID=int(t['nm_id']),price=t['price'],discount=t['discount']) for t in targets]);io.put(key,e)
    try:
        result=io.wb('/api/v2/upload/task','POST',e['request'])
        if type(result.get('id')) is not int or result['id']<=0:raise RuntimeError('No task receipt')
        e.update(upload_id=result['id'],upload_response=result,status='submitted');io.put(key,e)
    except Exception:
        e['status']='uncertain';io.put(key,e);raise RuntimeError('WB submission uncertain; no replay') from None
if e['status']=='submitted':
    for i in range(35):
        try:
            state=io.wb('/api/v2/history/tasks?uploadID='+str(e['upload_id']))
            if state.get('uploadID')!=e['upload_id']:raise RuntimeError('Task identity mismatch')
            if state.get('status') in [3,4,5,6]:
                details=io.wb('/api/v2/history/goods/task?uploadID='+str(e['upload_id'])+'&limit=1000&offset=0')
                fresh=io.prices([t['nm_id'] for t in targets])
                e.update(wb_state=state,wb_details=details,readback=fresh)
                good=state.get('status')==3 and state.get('successGoodsNumber')==2 and details.get('uploadID')==e['upload_id']
                for t in targets:
                    p=fresh[t['nm_id']]
                    rows=[g for g in details.get('historyGoods',[]) if str(g.get('nmID'))==t['nm_id']]
                    ok=(rows and all(not g.get('errorText') for g in rows) and p['vendorCode']==t['article'] and p.get('currencyIsoCode4217')=='CNY' and p.get('discount')==50 and p.get('clubDiscount')==e['before'][t['nm_id']].get('clubDiscount') and p.get('sizes') and all(Decimal(str(s['price']))==t['price'] and Decimal(str(s['discountedPrice']))==t['net'] for s in p['sizes']))
                    good=good and ok
                    io.put('china_agent:price_write_lock:v1:'+t['nm_id'],dict(execution=key,status='done' if ok else 'uncertain',upload_id=e['upload_id'],readback=p))
                e.update(status='done' if good else 'failed',completed_at=now().isoformat());io.put(key,e)
                print(json.dumps(e,ensure_ascii=False))
                if not good:raise SystemExit(1)
                break
        except SystemExit:raise
        except Exception:pass
        time.sleep(15)
    else:raise RuntimeError('WB still pending; do not resubmit')
