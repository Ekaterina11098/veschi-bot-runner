"""Scoped read-only reserve checks before proposals and again before execution."""
import copy, math, uuid
from datetime import datetime, timezone
from decimal import Decimal

def checks(io, items, stage):
    from china_advertising_v2 import http
    if stage not in ('prepare','send','execute'):raise ValueError('Unknown reserve stage')
    additions=[a for a in items if a.get('kind')=='ad_add_sku']
    if not additions:return dict(status='not_required',items=[])
    ids=sorted({a['campaign_id'] for a in additions})
    failure=None;body={}
    try:body=http(io,'/api/advert/v2/budget','POST',dict(advertIds=ids))
    except Exception as exc:failure=type(exc).__name__
    rows=body.get('adverts') if isinstance(body,dict) else None
    now=datetime.now(timezone.utc).isoformat();out=[]
    for a in additions:
        cid=a['campaign_id'];required=(a.get('growth_evidence')or{}).get('campaign_reserve_required_cny')
        found=[r for r in (rows if isinstance(rows,list) else []) if isinstance(r,dict) and r.get('advertId')==cid]
        actual=found[0].get('total') if len(found)==1 else None
        valid=lambda n:type(n)in(int,float) and math.isfinite(n) and n>=0
        code=('budget_unavailable' if failure or not isinstance(rows,list) or len(found)!=1 else
              'currency_mismatch' if found[0].get('currency')!='CNY' else
              'budget_invalid' if not valid(actual) else
              'reserve_invalid' if not valid(required) or required<=0 else
              'reserve_shortfall' if Decimal(str(actual)).quantize(Decimal('0.01'))<Decimal(str(required)).quantize(Decimal('0.01')) else 'ready')
        shortfall=float(max(Decimal(0),Decimal(str(required)).quantize(Decimal('0.01'))-Decimal(str(actual)).quantize(Decimal('0.01')))) if valid(actual) and valid(required) else None
        out.append(dict(id=a['id'],campaign_id=cid,nm_id=a['nm_id'],status=code,balance_cny=actual,
            required_cny=required,shortfall_cny=shortfall,observed_at=now))
    key='china_agent:reserve_preflight:v1:'+stage+':'+str(uuid.uuid4())
    value=dict(status=('ready_with_shortfall' if any(r['status']=='reserve_shortfall' for r in out) else 'ready') if all(r['status'] in ('ready','reserve_shortfall') for r in out) else 'blocked',stage=stage,
        observed_at=now,items=out,budget_response=body,read_error=failure,wb_writes=0,telegram_calls=0)
    if not io.create(key,value) or io.get(key)!=value:raise RuntimeError('Reserve audit readback failed')
    return dict(value,receipt_key=key)

def require(io,item):
    result=checks(io,[item],'execute');r=result['items'][0]
    if r['status'] in ('ready','reserve_shortfall'):return result
    if r['status']=='insufficient_balance':
        raise ValueError('Недостаточно резерва РК '+str(r['campaign_id'])+': баланс '+format(r['balance_cny'],'.2f')+' CNY, требуется '+format(r['required_cny'],'.2f')+' CNY, не хватает '+format(r['shortfall_cny'],'.2f')+' CNY.')
    raise ValueError('Резерв РК '+str(r['campaign_id'])+' не подтверждён: '+r['status']+'. Изменения не выполнены.')

def filter_bundle(io,bundle,stage):
    result=copy.deepcopy(bundle)
    actions={r['action']['id']:r['action'] for c in result['campaigns'] for r in c.get('focus',[]) if (r.get('action')or{}).get('kind')=='ad_add_sku'}
    evidence=checks(io,list(actions.values()),stage)
    failed={r['id']:r for r in evidence['items'] if r['status'] not in ('ready','reserve_shortfall')}
    for c in result['campaigns']:
        for r in c.get('focus',[]):
            a=r.get('action')or{}
            if a.get('id') in failed:
                r['action']=None;r['decision']='Добавление пока не готово: трёхдневный резерв бюджета не подтверждён.'
                r['reason']='';r['reserve_blocker']=failed[a['id']]
        c['attention']=[r for r in c.get('attention',[]) if (r.get('action')or{}).get('id') not in failed]
    result['reserve_preflight']=dict(receipt_key=evidence.get('receipt_key'),stage=stage,blocked_action_ids=sorted(failed))
    return result,evidence

def refresh_before_send(io,day,saved,key):
    """Never replace a report after any Telegram delivery has begun."""
    delivery=io.get('china_agent:advertising_delivery:'+day+':v1')or{}
    if delivery.get('parts'):return saved
    bundle,evidence=filter_bundle(io,saved['bundle'],'send')
    if evidence['status'] in ('ready','ready_with_shortfall','not_required'):return saved
    from china_advertising_v2_png import render
    from china_daily_ad_actions import plan
    import base64,hashlib,json
    slot='reserve-'+hashlib.sha256(json.dumps(bundle['reserve_preflight']['blocked_action_ids']).encode()).hexdigest()[:12]
    files=[]
    for index,f in enumerate(render(bundle)):
        p=plan(io,day,f,index,slot=slot)
        files.append(dict(kind=f['kind'],family=f['family'],page=f['page'],total=f['total'],plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],action_count=len(p['items']),b64=base64.b64encode(f['bytes']).decode()))
    archive=key+':before-'+slot
    if not io.get(archive):
        if not io.create(archive,saved):raise RuntimeError('Reserve artifact archive conflict')
    for f in saved['files']:
        pk='china_agent:loss_plan:v1:'+f['plan_id'];old=io.get(pk)
        if old:
            if old.get('report_message_ids'):raise RuntimeError('Cannot replace a visible proposal')
            old.update(invalidated_at=datetime.now(timezone.utc).isoformat(),invalidation_reason='Superseded before send after current reserve check')
            io.put(pk,old)
    updated=dict(saved,bundle=bundle,files=files,reserve_check=evidence['receipt_key'])
    io.put(key,updated)
    if io.get(key)!=updated:raise RuntimeError('Revised reserve report readback failed')
    return updated

