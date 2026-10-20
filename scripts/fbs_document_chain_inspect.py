import gzip,os,json,time,urllib.request,urllib.parse,urllib.error,datetime
MS='https://api.moysklad.ru/api/remap/1.2/'
WB='https://marketplace-api.wildberries.ru/'
report={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'mode':'read_only','errors':[],'credential_present':{k:bool(os.getenv(k)) for k in ['MOYSKLAD_API_TOKEN','WB_TOKEN_3']}}
def get(base,path,token,params=None):
    url=base+path
    if params:url+='?'+urllib.parse.urlencode(params)
    time.sleep(.25)
    req=urllib.request.Request(url,headers={'Authorization':('Bearer ' if base==MS else '')+token,'Accept-Encoding':'gzip','Accept':'application/json','User-Agent':'veschi-fbs-readonly/1'})
    try:
        with urllib.request.urlopen(req,timeout=40) as r:
            raw=r.read()
            if r.headers.get('Content-Encoding')=='gzip':raw=gzip.decompress(raw)
            return json.loads(raw)
    except urllib.error.HTTPError as e:raise RuntimeError('HTTP_'+str(e.code)+' '+path.split('?')[0])
def rows(path,params=None):
    out=[];offset=0
    while True:
        p=dict(params or {},limit=100,offset=offset)
        data=get(MS,path,os.environ['MOYSKLAD_API_TOKEN'],p)
        batch=data.get('rows',[]);out+=batch
        if len(out)>=data.get('meta',{}).get('size',len(out)):return out
        if not batch or len(out)>10000:raise RuntimeError('Pagination incomplete')
        offset+=len(batch)
def small(x):
    keys=['id','name','code','externalCode','meta','archived','applied','sum','moment','organization','agent','store','customerOrder','demand','salesReturns','demands','description','positions','vatEnabled','vatIncluded']
    return {k:x[k] for k in keys if k in x}
try:
    report['organizations']=[small(x) for x in rows('entity/organization')]
    report['stores']=[small(x) for x in rows('entity/store')]
    agents=rows('entity/counterparty',{'search':'Лазарев'})
    report['counterparties']=[small(x) for x in agents]
    report['recent_documents']={}
    for typ in ['customerorder','demand','salesreturn']:
        data=get(MS,'entity/'+typ,os.environ['MOYSKLAD_API_TOKEN'],{'limit':10,'order':'moment,desc'})
        report['recent_documents'][typ]=[small(x) for x in data.get('rows',[])]
    report['supply']=get(WB,'api/v3/supplies/WB-GI-286768405',os.environ['WB_TOKEN_3'])
except Exception as e:report['errors'].append(str(e) if isinstance(e,RuntimeError) else type(e).__name__)
key='fbs_document_chain:api_inspection:2026-10-20'
base=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/telegram_api_cache'
secret=os.environ['SUPABASE_SECRET_KEY']
headers={'apikey':secret,'Authorization':'Bearer '+secret,'Content-Type':'application/json','Prefer':'resolution=merge-duplicates,return=minimal'}
body={'cache_key':key,'payload':report,'expires_at':'2027-10-20T00:00:00Z','updated_at':report['observed_at']}
req=urllib.request.Request(base+'?on_conflict=cache_key',data=json.dumps(body).encode(),headers=headers,method='POST')
with urllib.request.urlopen(req,timeout=40) as r:assert r.status in (200,201,204)
print(json.dumps({'saved':True,'errors':report['errors'],'marketplace_writes':0,'moysklad_writes':0}))
