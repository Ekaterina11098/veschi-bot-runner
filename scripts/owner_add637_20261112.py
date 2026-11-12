"""One explicit owner instruction: add only637 at28minor, no funding or Telegram."""
import copy,json,os,time
from datetime import datetime,timezone
import requests
from china_advertising_state import AdvertisingIO
from china_advertising_full_growth import validate_addition

ROOT='china_agent:owner_add637:2026-11-12:v1'
PLAN='china_agent:loss_plan:v1:daily-2026-11-12-drr-0-buttons-4eda93157b431fd7f0f20546-5122667182'
CID=41298169;NM=1473242577;BID=28
def stamp():return datetime.now(timezone.utc).isoformat()
def verify(before,after):
    old={n['nm_id']:n for n in before['nm_settings']};new={n['nm_id']:n for n in after['nm_settings']}
    return (after['id']==CID and after['currency']=='CNY' and after['status']==before['status']==9
        and after['settings']==before['settings'] and set(new)==set(old)|{NM}
        and all(new[n]==v for n,v in old.items() if n!=NM)
        and new[NM]['subject']['id']==50 and new[NM]['bids_kopecks'].get('search')==BID
        and all(v==0 for zone,v in new[NM]['bids_kopecks'].items() if zone!='search'))

def main():
    if os.environ['GITHUB_REPOSITORY']!='Ekaterina11098/veschi-bot-runner' or os.environ['GITHUB_REF']!='refs/heads/main':raise ValueError('Exact public main required')
    io=AdvertisingIO();approval=io.get(ROOT+':approval')
    assert approval['owner_id']==5122667182 and approval['source_channel']=='codex' and approval['status']=='approved'
    assert approval['campaign_id']==CID and approval['nm_id']==NM and approval['target_minor']==BID
    assert approval['funding_allowed'] is False and approval['other_actions_allowed'] is False and approval['telegram_allowed'] is False
    original=io.get(PLAN);items=[i for i in original['items'] if i['id']=='41298169:add:1473242577']
    assert len(items)==1;item=copy.deepcopy(items[0])
    assert (item['campaign_id'],item['nm_id'],item['target_minor'],item['placement'],item['kind'])==(CID,NM,BID,'search','ad_add_sku')
    state=io.get(ROOT+':execution')
    if state:
        if state['status']=='verified':print('Already WB verified; no mutations');return
        raise RuntimeError('Existing execution requires read-only reconciliation; no blind retry')
    state=dict(status='preflight',approval_key=ROOT+':approval',source_plan=PLAN,item=item,started_at=stamp(),wb_writes=0,funding_cny=0,telegram_calls=0)
    assert io.create(ROOT+':execution',state)
    def save():io.put(ROOT+':execution',state)
    def request(path,method='GET',body=None):
        allowed=(method=='GET' and path=='/api/advert/v2/adverts?ids='+str(CID)) or (method=='PATCH' and (
            path=='/adv/v0/auction/nms' and body==dict(nms=[dict(advert_id=CID,nms=dict(add=[NM],delete=[]))]) or
            path=='/api/advert/v1/bids' and body==dict(bids=[dict(advert_id=CID,nm_bids=[dict(nm_id=NM,placement='search',bid_kopecks=BID)])])))
        if not allowed:raise ValueError('Owner action scope exceeded')
        time.sleep(1.5)
        r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=50)
        if not r.ok:raise RuntimeError('WB advertising HTTP '+str(r.status_code))
        return r.json() if r.content else {}
    def read():
        rows=request('/api/advert/v2/adverts?ids='+str(CID)).get('adverts',[])
        if len(rows)!=1 or rows[0]['id']!=CID or rows[0]['currency']!='CNY':raise ValueError('Exact campaign readback unavailable')
        return rows[0]
    try:
        before=read();state['before']=before;save()
        present=next((n for n in before['nm_settings'] if n['nm_id']==NM),None)
        if present:
            if not verify(before,before):raise ValueError('SKU already present at different configuration; no overwrite')
            state.update(status='verified',already_present=True,after=before,verified_at=stamp());save()
        else:
            io.daily_report_current_revalidation=True
            validate_addition(io,item,before)
            state.update(status='preflight_verified',preflight_at=stamp());save()
            state['add_phase']='submitting';state['status']='submitting';save()
            state['add_response']=request('/adv/v0/auction/nms','PATCH',dict(nms=[dict(advert_id=CID,nms=dict(add=[NM],delete=[]))]))
            state['wb_writes']+=1;state['add_phase']='accepted';state['status']='accepted';save()
            for _ in range(6):
                after=read();state['after']=after;save()
                if any(n['nm_id']==NM for n in after['nm_settings']):break
                time.sleep(2)
            else:raise RuntimeError('Added SKU not visible; do not replay')
            old={n['nm_id']:n for n in before['nm_settings']};new={n['nm_id']:n for n in after['nm_settings']}
            if set(new)!=set(old)|{NM} or any(new[n]!=v for n,v in old.items()) or after['settings']!=before['settings'] or after['status']!=9:raise RuntimeError('Campaign changed during addition; reconcile only')
            if new[NM]['bids_kopecks'].get('search')!=BID:
                state['bid_phase']='submitting';save()
                state['bid_response']=request('/api/advert/v1/bids','PATCH',dict(bids=[dict(advert_id=CID,nm_bids=[dict(nm_id=NM,placement='search',bid_kopecks=BID)])]))
                state['wb_writes']+=1;state['bid_phase']='accepted';save()
            for _ in range(6):
                after=read();state['after']=after;save()
                if verify(before,after):break
                time.sleep(2)
            else:raise RuntimeError('Final WB state differs; no replay')
            state.update(status='verified',verified_at=stamp());save()
        registry=io.get('china_agent:verified_campaign_state:v1') or {}
        registry[str(CID)]=ROOT+':execution';io.put('china_agent:verified_campaign_state:v1',registry)
        assert io.get(ROOT+':execution')['status']=='verified'
        print(json.dumps(dict(status='verified',campaign_id=CID,nm_id=NM,search_bid_cny=.28,wb_writes=state['wb_writes'],funding_cny=0,telegram_calls=0)))
    except Exception as exc:
        state.update(status='uncertain' if state.get('add_phase') in ('submitting','accepted') else 'blocked',error_type=type(exc).__name__,reason=str(exc) if isinstance(exc,(ValueError,RuntimeError)) else 'Preflight error',finished_at=stamp());save()
        raise
if __name__=='__main__':main()
