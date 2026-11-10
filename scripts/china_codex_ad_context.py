"""Small dated advertising evidence for cloud reasoning. Cache reads only, no writes."""
import re
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
def context(db,text,day):
    source=db.get('china_agent:advertising_source:'+day+':v2') or {}
    if source.get('cabinet')!='token_3':return dict(status='unavailable',reason='No scoped daily advertising cache',wb_reads=0)
    inputs=db.get('china_agent:advertising_full_growth:'+day+':v1:inputs')or{}
    registry=db.get('china_agent:verified_campaign_state:v1')or{}
    states={c['id']:c for b in source.get('batches',{}).values()for c in b.get('campaigns',{}).get('adverts',[])}
    stats={c['advertId']:c for b in source.get('batches',{}).values()for c in b.get('stats',[])}
    labels={r['nmID']:r.get('vendorCode','nmID '+str(r['nmID']))for r in source.get('catalogue',{}).get('rows',[])}
    requested=[int(v)for v in re.findall(r'(?<!\d)\d{7,9}(?!\d)',text)if int(v)in states]
    ids=list(dict.fromkeys(requested))[:3] or sorted(states,key=lambda cid:stats.get(cid,{}).get('sum',0),reverse=True)[:3]
    result=[]
    for cid in ids:
        state=states[cid];receipt=None
        key=registry.get(str(cid))
        if isinstance(key,str):
            r=db.get(key)or{}
            if r.get('status')=='verified'and r.get('after',{}).get('id')==cid:
                state=r['after'];receipt=dict(cache_key=key,status='verified',at=r.get('verified_at')or r.get('completed_at'),before_members=[n['nm_id']for n in r.get('before',{}).get('nm_settings',[])],after_members=[n['nm_id']for n in state.get('nm_settings',[])])
        members={n['nm_id']:n for n in state.get('nm_settings',[])}
        daily={}
        for d in stats.get(cid,{}).get('days',[]):
            for a in d.get('apps',[]):
                for n in a.get('nms',[]):
                    if n.get('sum',0)<=0 and n.get('orders',0)<=0:continue
                    nm=n['nmId'];row=daily.setdefault((d['date'][:10],nm),dict(date=d['date'][:10],nm_id=nm,spend=0,clicks=0,baskets=0,orders=0,amount=0))
                    for k,v in [('spend','sum'),('clicks','clicks'),('baskets','atbs'),('orders','orders'),('amount','sum_price')]:row[k]+=n.get(v,0)
        spend={}
        for r in daily.values():spend[r['nm_id']]=spend.get(r['nm_id'],0)+r['spend']
        chosen=sorted(set(members)|set(spend),key=lambda n:spend.get(n,0),reverse=True)[:8]
        model=inputs.get('economics',{}).get('rows',{})
        rows=[]
        for nm in chosen:
            e=model.get(str(nm),{})
            rows.append(dict(nm_id=nm,article=labels.get(nm,'nmID '+str(nm)),currently_member=nm in members,bids_minor=members.get(nm,{}).get('bids_kopecks'),daily=[r for r in daily.values()if r['nm_id']==nm],economics={k:e.get(k)for k in ('seller_price_cny','own_cogs_rub','buyout','sample_size','expected_margin_before_ads_cny','unknown_reverse_and_shared_costs','stock_free','published_stock','observed_at','price_observed_at','stock_observed_at')}))
        result.append(dict(campaign_id=cid,status=state.get('status'),placements=state.get('settings',{}).get('placements'),latest_started=state.get('timestamps',{}).get('started'),receipt=receipt,member_count=len(members),rows=rows,sku_coverage='partial'if len(set(members)|set(spend))>8 else'complete'))
    return dict(status='available',cabinet='token_3',source_key='china_agent:advertising_source:'+day+':v2',source_observed_at=source.get('observed_at'),period_from=source.get('period_from'),period_to=source.get('period_to'),campaigns=result,campaign_coverage='scoped'if requested else'top3_by_saved_spend_not_whole_cabinet',wb_reads=0,execution_permission=False,note='Canonical membership overrides older statistics; retain removed SKU costs but never exclude again. No-order DRR undefined. Mixed launch/change days are risk diagnostics, not stable full days.')
