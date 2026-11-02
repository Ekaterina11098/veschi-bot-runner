"""Dated owner-approved OOO execution. Private manifest; no price/TG writes."""
import os,sys,time,json,hashlib,datetime,copy,base64,requests
from pathlib import Path
sys.path.insert(0,str(Path('private-source').resolve()))
from analytics.collect import database
ROOT='ooo_agent:full_ad_plan:2026-11-02:v1'
KEY=ROOT+':apply_all'
TOKEN=os.environ['WB_TOKEN_1']
HASH='f6ad8c9b9cd1cd42495579f731677697207a1f8960e63792b95f41cdfd099b72'
HOST='advert-api.wildberries.ru'
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def get(key):
    rows=database('GET','telegram_api_cache',params={'cache_key':'eq.'+key,'select':'payload','limit':1}) or []
    return rows[0]['payload'] if rows else None
def put(key,value):
    database('POST','telegram_api_cache',params={'on_conflict':'cache_key'},body={'cache_key':key,'payload':value,'updated_at':stamp(),'expires_at':'2036-11-02T00:00:00Z'})
    if get(key)!=json.loads(json.dumps(value)):raise RuntimeError('Private receipt readback mismatch')
def claim(value):
    secret=os.environ['SUPABASE_SECRET_KEY']
    h={'apikey':secret,'Content-Type':'application/json','Prefer':'resolution=ignore-duplicates,return=representation'}
    if not secret.startswith('sb_secret_'):h['Authorization']='Bearer '+secret
    r=requests.post(os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/telegram_api_cache',headers=h,params={'on_conflict':'cache_key'},json={'cache_key':KEY,'payload':value,'updated_at':stamp(),'expires_at':'2036-11-02T00:00:00Z'},timeout=45)
    r.raise_for_status()
    return bool(r.json())
def save():put(KEY,state)
def authorize():
    a=get(ROOT+':authorization')
    if not a or a.get('status')!='approved' or a.get('cabinet')!='token_1' or a.get('plan_sha256')!=HASH:raise PermissionError('Exact private owner approval required')
    if datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(a['expires_at']):raise PermissionError('Dated authorization expired')
    if a.get('sku_spend_caps_enabled') or not a.get('no_automatic_topups'):raise PermissionError('Scope changed')
    return a
def wait_until(until,path):
    if until>time.time():
        state.update(status='waiting_provider',waiting_path=path,resume_after=datetime.datetime.fromtimestamp(until,datetime.timezone.utc).isoformat());save()
    while time.time()<until:
        authorize()
        time.sleep(min(45,max(.1,until-time.time())))
def req(path,method='GET',body=None,step=None):
    bare=path.split('?')[0]
    reads={('GET','/adv/v1/promotion/count'),('GET','/api/advert/v2/adverts'),('GET','/adv/v1/balance'),('POST','/api/advert/v2/budget'),('POST','/api/advert/v1/bids/min'),('GET','/api/advert/v0/daily-limits')}
    writes={('PATCH','/adv/v0/auction/nms'),('PATCH','/api/advert/v1/bids'),('POST','/adv/v2/seacat/save-ad'),('PUT','/api/advert/v0/daily-limits'),('POST','/adv/v1/budget/deposit'),('GET','/adv/v0/start')}
    if (method,bare) not in (writes if step else reads):raise PermissionError('Endpoint outside frozen scope')
    if step and step in state['steps']:raise RuntimeError('Write replay refused: '+step)
    pausekey='wb-pause:'+hashlib.sha256((TOKEN+HOST+bare).encode()).hexdigest()
    for attempt in range(4):
        wait_until(float((get(pausekey) or {}).get('until',0)),bare)
        authorize()
        if step:
            state['steps'][step]={'status':'submitting','path':path,'method':method,'body':body,'submitted_at':stamp()};save()
        time.sleep(2)
        try:r=requests.request(method,'https://'+HOST+path,headers={'Authorization':TOKEN,'Content-Type':'application/json'},json=body,timeout=(10,60),allow_redirects=False)
        except requests.RequestException:
            if step:state['steps'][step].update(status='uncertain',error='Transport outcome unknown');save()
            raise RuntimeError('Unknown transport outcome; no blind write retry') from None
        raw=r.headers.get('Retry-After') or r.headers.get('X-Ratelimit-Retry') or r.headers.get('X-Ratelimit-Reset')
        try:delay=float(raw) if raw is not None else 0
        except ValueError:delay=0
        if delay>time.time()-86400:delay=max(0,delay-time.time())
        if r.status_code==429 or (r.headers.get('X-Ratelimit-Remaining')=='0' and delay>0):
            until=time.time()+max(delay,60 if r.status_code==429 else 2)+3
            old=get(pausekey) or {}
            put(pausekey,{'until':max(until,float(old.get('until',0))),'basis':'provider_header'})
        if r.status_code==429:
            if step:
                state['steps'][step].update(status='rejected_429');save()
                # A money/create request is never resubmitted by this executor.
                raise RuntimeError('Write explicitly rejected 429; retained for reviewed continuation')
            continue
        if not r.ok:
            if step:state['steps'][step].update(status='rejected',http_status=r.status_code);save()
            raise RuntimeError('WB HTTP '+str(r.status_code)+' at '+bare)
        value=r.json() if r.content else {}
        if step:state['steps'][step].update(status='accepted',response=value,accepted_at=stamp());save()
        state['status']='executing';save()
        return value
    raise RuntimeError('Read remained rate limited; state preserved')
def configs(ids):
    cs={c['id']:c for c in req('/api/advert/v2/adverts?ids='+','.join(map(str,ids))).get('adverts',[])}
    if set(cs)!=set(ids):raise RuntimeError('Incomplete configuration readback')
    return cs
def minima(cid,ids,placements):
    j=req('/api/advert/v1/bids/min','POST',dict(advert_id=cid,nm_ids=sorted(ids),payment_type='cpc',placement_types=placements))
    out={}
    for row in j.get('bids',[]):
        out[row['nm_id']]={}
        for p in placements:
            matches=[b for b in row.get('bids',[]) if b.get('type')==p and b.get('currency')=='KGS']
            if len(matches)!=1:raise RuntimeError('Minimum currency or placement ambiguous')
            out[row['nm_id']][p]=matches[0]['value']
    if set(out)!=set(ids):raise RuntimeError('Incomplete exact SKU minima')
    state.setdefault('minimums',{})[str(cid)]=j;save()
    return out
def inventory():
    j=req('/adv/v1/promotion/count');out={}
    for group in j.get('adverts',[]):
        for c in group.get('advert_list',[]):out[c['advertId']]=group['status']
    state['inventory']={'observed_at':stamp(),'statuses':out};save()
    return out
def budget(ids):
    rows=req('/api/advert/v2/budget','POST',{'advertIds':ids}).get('adverts',[])
    if {r['advertId'] for r in rows}!=set(ids) or any(r.get('currency')!='KGS' for r in rows):raise RuntimeError('Budget currency/readback incomplete')
    return {r['advertId']:r['total'] for r in rows}
def member_ids(c):return {n['nm_id'] for n in c['nm_settings']}
def verify(cs,before,expected,bid_updates,new_specs):
    for cid,c in cs.items():
        if c.get('currency')!='KGS' or c.get('bid_type')!='manual':raise RuntimeError('Unexpected currency/bid model')
        if member_ids(c)!=expected[cid]:raise RuntimeError('Membership readback mismatch '+str(cid))
        if cid in before:
            for k in ('settings','restrictions'):
                if c.get(k)!=before[cid].get(k):raise RuntimeError('Unapproved configuration change '+str(cid))
            wanted_status=11 if cid==39605582 else before[cid]['status']
            if c['status']!=wanted_status:raise RuntimeError('Unexpected campaign status '+str(cid))
        else:
            spec=new_specs[cid]
            if c['status']!=4 or c['settings'].get('name')!=spec['name'] or c['settings'].get('payment_type')!='cpc' or c['settings'].get('placements')!={'search':True,'recommendations':False}:raise RuntimeError('New draft configuration mismatch')
        originals={n['nm_id']:n for n in before.get(cid,{}).get('nm_settings',[])}
        for n in c['nm_settings']:
            for p,v in bid_updates.get(cid,{}).get(n['nm_id'],{}).items():
                if n['bids_kopecks'].get(p)!=v:raise RuntimeError('Bid readback mismatch')
            if n['nm_id'] in originals:
                for p,v in originals[n['nm_id']]['bids_kopecks'].items():
                    if p not in bid_updates.get(cid,{}).get(n['nm_id'],{}) and n['bids_kopecks'].get(p)!=v:raise RuntimeError('Untargeted bid changed')
    return True
def main():
    a=authorize()
    pre=get(ROOT+':preflight_cost_reduction') or {}
    if pre.get('authorization_sha256')!=HASH or not all(pre.get('identity_checks',{}).values()) or not pre.get('before'):raise PermissionError('Verified identity and baseline required')
    claims=json.loads(base64.urlsafe_b64decode(TOKEN.split('.')[1]+'==='))
    if claims.get('exp',0)<time.time() or claims.get('t') is not False or int(claims.get('s',0))&(1<<30):raise PermissionError('Token validity/write capability')
    identities=database('GET','analytics_snapshots',params={'cabinet':'eq.token_1','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100}) or []
    if not claims.get('sid') or {r['payload'].get('sid') for r in identities}!={claims['sid']}:raise PermissionError('Seller identity mismatch')
    before={int(k):v for k,v in pre['before'].items()}
    groups={g:sorted(r['nm'] for r in a['approved_candidates'] if r['group']==g) for g in ['G01','G04','G05','G06','G07','G08','G09','G10','G11']}
    if len(a['approved_candidates'])!=122 or any(r['free']<5 or r['margin40']<=0 or r['cost']<=0 for r in a['approved_candidates']):raise PermissionError('Eligibility boundary')
    current=inventory()
    if current.get(39605582)!=11 or current.get(40385586)!=11 or any(current.get(cid)!=9 for cid in (39605579,39605581)):raise RuntimeError('Expected paused CPM/Noel and active CPC status not confirmed')
    state['cpm_pause_verified_at']=stamp();state['before']=pre['before'];save()
    # This deletion reduces exposure and does not depend on a bid quote.
    remove=sorted(set(a['cpm_remove_nm_ids'])&member_ids(before[39605582]))
    if len(remove)!=11 or len(member_ids(before[39605582])-set(remove))<1:raise RuntimeError('CPM removal boundary')
    req('/adv/v0/auction/nms','PATCH',{'nms':[{'advert_id':39605582,'nms':{'add':[],'delete':remove}}]},'remove_cpm_11')
    # Empty-budget drafts are created before any money transfer or activation.
    new_specs={}
    for g in ['G06','G07','G08','G09','G10']:
        name='VESCHI OOO '+g+' CPC 20261102 f6ad8c9b'
        value=req('/adv/v2/seacat/save-ad','POST',dict(name=name,nms=groups[g],bid_type='manual',payment_type='cpc',placement_types=['search']),'create_'+g)
        cid=value if isinstance(value,int) else value.get('advertId') if isinstance(value,dict) else None
        if not isinstance(cid,int) or cid in before or cid in new_specs:raise RuntimeError('Creation result ambiguous; no replay')
        new_specs[cid]={'group':g,'name':name,'ids':groups[g],'budget':a['new_and_returned_budget_kgs'][g]}
        state['new_campaigns']={str(k):v for k,v in new_specs.items()};save()
    updates={};expected={cid:member_ids(c) for cid,c in before.items()}
    expected[39605582]-=set(remove)
    memberships=[]
    def add_bid(cid,nm,p,v):updates.setdefault(cid,{}).setdefault(nm,{})[p]=v
    bag_ids=set(groups['G05'])|{r['nm'] for r in a['approved_candidates'] if r['group']=='G01' and '-Zont-' not in r['article']}|{851316021}
    quote=minima(39605581,bag_ids,['search','recommendation'])
    for nm in groups['G05']:
        if any(v>325 for v in quote[nm].values()):raise RuntimeError('Approved bag bid below native minimum')
        for p in ('search','recommendations'):add_bid(39605581,nm,p,325)
    for r in a['approved_candidates']:
        if r['group']=='G01' and '-Zont-' not in r['article']:
            if quote[r['nm']]['search']>360:raise RuntimeError('Approved raise below native minimum')
            add_bid(39605581,r['nm'],'search',360)
    lower_allowed=all(v<=260 for v in quote[851316021].values())
    deletes=[] if lower_allowed else [851316021]
    if lower_allowed:
        for p in ('search','recommendations'):add_bid(39605581,851316021,p,260)
    memberships.append({'advert_id':39605581,'nms':{'add':sorted(set(groups['G05'])-expected[39605581]),'delete':deletes}})
    expected[39605581]=(expected[39605581]|set(groups['G05']))-set(deletes)
    zraise=[r['nm'] for r in a['approved_candidates'] if r['group']=='G01' and '-Zont-' in r['article']]
    q=minima(39605579,set(groups['G11'])|set(zraise),['recommendation'])
    for nm in groups['G11']+zraise:
        v=300 if nm in zraise else 270
        if q[nm]['recommendation']>v:raise RuntimeError('Approved umbrella bid below native minimum')
        add_bid(39605579,nm,'recommendations',v)
    memberships.append({'advert_id':39605579,'nms':{'add':sorted(set(groups['G11'])-expected[39605579]),'delete':[]}})
    expected[39605579]|=set(groups['G11'])
    q=minima(40385586,set(groups['G04']),['search','recommendation'])
    for nm in groups['G04']:
        if any(v>325 for v in q[nm].values()):raise RuntimeError('Noel approved bid below native minimum')
        for p in ('search','recommendations'):add_bid(40385586,nm,p,325)
    memberships.append({'advert_id':40385586,'nms':{'add':sorted(set(groups['G04'])-expected[40385586]),'delete':sorted(expected[40385586]-set(groups['G04']))}})
    expected[40385586]=set(groups['G04'])
    for cid,spec in new_specs.items():
        q=minima(cid,set(spec['ids']),['search'])
        if any(v['search']>325 for v in q.values()):raise RuntimeError('New campaign approved bid below native minimum')
        for nm in spec['ids']:add_bid(cid,nm,'search',325)
        expected[cid]=set(spec['ids'])
    state['expected_memberships']={str(k):sorted(v) for k,v in expected.items()};state['bid_updates']=updates;save()
    req('/adv/v0/auction/nms','PATCH',{'nms':memberships},'update_memberships')
    bids=[{'advert_id':cid,'nm_bids':[{'nm_id':nm,'bid_kopecks':v,'placement':p} for nm,ps in ns.items() for p,v in ps.items()]} for cid,ns in updates.items()]
    req('/api/advert/v1/bids','PATCH',{'bids':bids},'apply_approved_bids')
    funding={40385586:a['new_and_returned_budget_kgs']['G04']}|{cid:s['budget'] for cid,s in new_specs.items()}
    if sum(funding.values())!=12000 or sum(funding.values())>a['max_new_and_returned_campaign_budget_kgs']:raise PermissionError('Funding ceiling')
    for cid,amount in funding.items():req('/api/advert/v0/daily-limits','PUT',dict(advertIds=[cid],enabled=True,dailyLimit=amount*100,carryOverEnabled=False),'limit_'+str(cid))
    cs=configs(sorted(expected))
    verify(cs,before,expected,updates,new_specs)
    state['configuration_readback']={str(k):v for k,v in cs.items()};state['configuration_verified_at']=stamp();save()
    limits=req('/api/advert/v0/daily-limits?advertIds='+','.join(map(str,funding))).get('adverts',[])
    if {r['advertId'] for r in limits}!=set(funding):raise RuntimeError('Incomplete daily limits')
    for r in limits:
        if r.get('currency')!='KGS' or r.get('enabled') is not True or r.get('carryOverEnabled') is not False or r.get('dailyLimit')!=funding[r['advertId']]*100 or r.get('valid') is False:raise RuntimeError('Campaign daily limit unverified')
    baseline=budget(list(funding))
    if any(v!=0 for v in baseline.values()):raise RuntimeError('Nonzero draft/Noel budget; no duplicate deposit')
    wallet=req('/adv/v1/balance')
    if wallet.get('currency')!='KGS':raise RuntimeError('Wallet currency mismatch')
    source=0 if wallet.get('balance',0)>=12000 else 1 if wallet.get('net',0)>=12000 else None
    if source is None:raise RuntimeError('Insufficient single-source wallet for full approved funding')
    state['funding_before']=baseline;state['funding_source']=source;save()
    for cid,amount in funding.items():req('/adv/v1/budget/deposit?id='+str(cid),'POST',dict(sum=amount,type=source),'deposit_'+str(cid))
    after=budget(list(funding))
    if after!=funding:raise RuntimeError('Funding readback mismatch; no starts')
    state['funding_verified_at']=stamp();state['funding_after']=after;save()
    for cid in funding:req('/adv/v0/start?id='+str(cid),step='start_'+str(cid))
    statuses=inventory()
    if any(statuses.get(cid)!=9 for cid in funding) or statuses.get(39605582)!=11:raise RuntimeError('Activation status readback pending or mismatched')
    state.update(status='complete',completed_at=stamp(),drr_target_pct=5,drr_control_order=['campaign','sku'],first_full_post_change_day=(datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).date()+datetime.timedelta(days=1)).isoformat())
    save()
if __name__=='__main__':
    if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise PermissionError('Public main only')
    state={'status':'starting','started_at':stamp(),'run_id':os.environ['GITHUB_RUN_ID'],'authorization_sha256':HASH,'steps':{},'telegram_calls':0}
    if not claim(state):
        previous=get(KEY) or {}
        if previous.get('run_id')=='41469488891' and previous.get('status')=='attention' and previous.get('error')=='Private receipt readback mismatch' and previous.get('steps')=={}:
            state['recovered_readonly_run']='41469488891';save()
        else:print('Existing executor receipt preserved; no replay');sys.exit(0)
    try:main()
    except Exception as e:state.update(status='attention',error=str(e) if isinstance(e,(RuntimeError,ValueError,PermissionError)) else type(e).__name__);save()
    print(json.dumps({'status':state['status'],'accepted_writes':sum(v['status']=='accepted' for v in state['steps'].values()),'telegram_calls':0}),flush=True)

