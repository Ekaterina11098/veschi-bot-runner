"""OOO owner execution preflight and explicit cost reduction. No creation/funding yet."""
import os,sys,time,json,base64,hashlib,datetime,copy,requests
from pathlib import Path
sys.path.insert(0,str(Path("private-source").resolve()))
from analytics.collect import database
ROOT="ooo_agent:full_ad_plan:2026-11-02:v1"
KEY=ROOT+":preflight_cost_reduction"
TOKEN=os.environ["WB_TOKEN_1"]
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def cache_get(key):
    rows=database("GET","telegram_api_cache",params={"cache_key":"eq."+key,"select":"payload","limit":1}) or []
    return rows[0]["payload"] if rows else None
def cache_put(key,value):
    database("POST","telegram_api_cache",params={"on_conflict":"cache_key"},body={"cache_key":key,"payload":value,"updated_at":stamp(),"expires_at":"2036-11-02T00:00:00Z"})
    if cache_get(key)!=value:raise RuntimeError("Private state readback mismatch")
def create(key,value):
    url=os.environ["SUPABASE_URL"].rstrip("/")+"/rest/v1/telegram_api_cache"
    secret=os.environ["SUPABASE_SECRET_KEY"]
    h={"apikey":secret,"Content-Type":"application/json","Prefer":"resolution=ignore-duplicates,return=representation"}
    if not secret.startswith("sb_secret_"):h["Authorization"]="Bearer "+secret
    r=requests.post(url,params={"on_conflict":"cache_key"},headers=h,json={"cache_key":key,"payload":value,"updated_at":stamp(),"expires_at":"2036-11-02T00:00:00Z"},timeout=45)
    if not r.ok:raise RuntimeError("Private claim HTTP "+str(r.status_code))
    return bool(r.json())
def latest(source):
    rows=database("GET","analytics_snapshots",params={"cabinet":"eq.token_1","source":"eq."+source,"status":"eq.complete","select":"payload","order":"id.desc","limit":1}) or []
    if not rows:raise RuntimeError("Private source unavailable: "+source)
    return rows[0]["payload"]
state={"status":"preflight","started_at":stamp(),"run_id":os.environ["GITHUB_RUN_ID"],"wb_write_attempts":0,"steps":{},"telegram_calls":0}
if os.environ.get("GITHUB_REPOSITORY")!="Ekaterina11098/veschi-bot-runner" or os.environ.get("GITHUB_REF")!="refs/heads/main":raise PermissionError("Public main only")
if not create(KEY,state):print("Existing execution receipt preserved; no replay");sys.exit(0)
def save():cache_put(KEY,state)
def request(path,method="GET",body=None,write=False):
    bare=path.split("?")[0]
    allowed_reads={("/api/advert/v2/adverts","GET"),("/api/advert/v2/budget","POST"),("/adv/v1/balance","GET"),("/api/advert/v0/daily-limits","GET"),("/api/advert/v1/bids/min","POST")}
    allowed_writes={("/adv/v0/pause","GET"),("/adv/v0/auction/nms","PATCH")}
    if (bare,method) not in (allowed_writes if write else allowed_reads):raise PermissionError("Endpoint not authorized")
    pausekey="wb-pause:"+hashlib.sha256((TOKEN+"advert-api.wildberries.ru"+bare).encode()).hexdigest()
    pause=cache_get(pausekey) or {}
    if float(pause.get("until",0))>time.time():raise RuntimeError("Shared WB cooldown; retry after "+str(int(pause["until"]-time.time())+1)+" seconds")
    time.sleep(1.6)
    try:r=requests.request(method,"https://advert-api.wildberries.ru"+path,headers={"Authorization":TOKEN,"Content-Type":"application/json"},json=body,timeout=(10,55),allow_redirects=False)
    except requests.RequestException:raise RuntimeError("WB outcome unknown; no automatic write retry") from None
    if r.status_code==429:
        value=r.headers.get("Retry-After") or r.headers.get("X-Ratelimit-Retry") or r.headers.get("X-Ratelimit-Reset") or "900"
        try:seconds=max(1,int(float(value)))
        except ValueError:seconds=900
        cache_put(pausekey,{"until":time.time()+seconds+2,"basis":"provider_header"})
        raise RuntimeError("WB HTTP 429; provider wait "+str(seconds)+" seconds")
    if not r.ok:raise RuntimeError("WB HTTP "+str(r.status_code))
    return r.json() if r.content else {}
def config(ids):
    value=request("/api/advert/v2/adverts?ids="+",".join(map(str,ids)))
    cs={c["id"]:c for c in value.get("adverts",[])}
    if set(cs)!=set(ids):raise RuntimeError("Incomplete WB configuration")
    return cs
def projection(c):
    return {k:copy.deepcopy(c.get(k)) for k in ("id","status","currency","bid_type","settings","restrictions")}|{"nm_settings":sorted(copy.deepcopy(c["nm_settings"]),key=lambda n:n["nm_id"])}
def verify_cpm_state(before,after,remove):
    expected=copy.deepcopy(before)
    expected["status"]=11
    expected["nm_settings"]=[n for n in expected["nm_settings"] if n["nm_id"] not in set(remove)]
    if not expected["nm_settings"] or projection(expected)!=projection(after):raise RuntimeError("CPM exact permitted-difference check failed")
    return True
def write(name,path,method,body=None):
    live=cache_get(ROOT+":authorization")
    if not live or live.get("status")!="approved" or live.get("plan_sha256")!=state.get("authorization_sha256"):raise PermissionError("Owner authorization changed")
    if datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(live["expires_at"]):raise PermissionError("Approval expired")
    if name in state["steps"]:raise RuntimeError("Prior step exists; readback only")
    state["steps"][name]={"status":"submitting","path":path,"method":method,"body":body,"submitted_at":stamp()}
    state["wb_write_attempts"]+=1;save()
    try:
        value=request(path,method,body,write=True)
        state["steps"][name].update(status="accepted",response=value,accepted_at=stamp());save();return value
    except Exception as exc:
        state["steps"][name].update(status="uncertain",error=str(exc));save();raise
try:
    authorization=cache_get(ROOT+":authorization")
    if not authorization or authorization.get("status")!="approved" or authorization.get("cabinet")!="token_1" or authorization.get("source_quote")!="делай все, пробуем":raise PermissionError("Owner exact approval missing")
    state["authorization_sha256"]=authorization["plan_sha256"]
    claims=json.loads(base64.urlsafe_b64decode(TOKEN.split(".")[1]+"==="))
    identities=database("GET","analytics_snapshots",params={"cabinet":"eq.token_1","source":"eq.seller_identity","status":"eq.complete","select":"payload","limit":100}) or []
    sid=claims.get("sid")
    checks={"not_expired":claims.get("exp",0)>time.time(),"not_test":claims.get("t") is False,"write_not_disabled":not bool(int(claims.get("s",0))&(1<<30)),"seller_identity_matches":bool(sid) and {x["payload"].get("sid") for x in identities}=={sid}}
    state["identity_checks"]=checks;save()
    if not all(checks.values()):raise PermissionError("OOO token identity/write capability check failed")
    before=config([39605579,39605581,39605582,40385586])
    if any(c.get("currency")!="KGS" or c.get("bid_type")!="manual" for c in before.values()):raise PermissionError("Unexpected account/campaign currency or bid model")
    state["before"]={str(cid):c for cid,c in before.items()};save()
    # Explicit pause and eleven removals from the approved CPM. No new exposure.
    c=before[39605582]
    if c["settings"]["payment_type"]!="cpm" or c["settings"]["name"]!="!!ИИПоказы полки":raise PermissionError("CPM identity changed")
    if c["status"]==9:
        write("pause_cpm","/adv/v0/pause?id=39605582","GET")
        after=config([39605582])[39605582];state["pause_readback"]=after
        verify_cpm_state(c,after,[])
        state["steps"]["pause_cpm"]["status"]="verified";save()
    elif c["status"]==11:state["steps"]["pause_cpm"]={"status":"already_paused_verified"};save()
    else:raise RuntimeError("Unexpected CPM state")
    remove=set(authorization["cpm_remove_nm_ids"])
    present={n["nm_id"] for n in c["nm_settings"]};deletes=sorted(remove&present)
    if deletes:
        if not c.get("restrictions",{}).get("can_change_nms") or not(present-remove):raise RuntimeError("CPM membership boundary")
        write("remove_cpm","/adv/v0/auction/nms","PATCH",{"nms":[{"advert_id":39605582,"nms":{"add":[],"delete":deletes}}]})
        after=config([39605582])[39605582];state["cpm_after"]=after
        if {n["nm_id"] for n in after["nm_settings"]}!=present-remove or after["status"]!=11:raise RuntimeError("CPM removal readback mismatch")
        verify_cpm_state(c,after,remove)
        state["steps"]["remove_cpm"]["status"]="verified";save()
    else:state["steps"]["remove_cpm"]={"status":"already_absent_verified"};save()
    for label,path,method,body in [
        ("wallet","/adv/v1/balance","GET",None),
        ("budgets","/api/advert/v2/budget","POST",{"advertIds":sorted(before)}),
        ("daily_limits","/api/advert/v0/daily-limits?advertIds=39605579,39605581,40385586","GET",None),
        ("bag_minimums","/api/advert/v1/bids/min","POST",{"advert_id":39605581,"nm_ids":sorted(set(authorization["bag_candidate_nm_ids"])|{n["nm_id"] for n in before[39605581]["nm_settings"]}),"payment_type":"cpc","placement_types":["search","recommendation"]}),
    ]:
        try:state[label]={"status":"received","data":request(path,method,body),"observed_at":stamp()}
        except Exception as exc:state[label]={"status":"unavailable","error":str(exc),"observed_at":stamp()}
        save()
    state["status"]="cost_reduction_verified_preflight_complete"
except Exception as exc:
    state.update(status="attention",error=str(exc) if isinstance(exc,(PermissionError,RuntimeError,ValueError)) else type(exc).__name__)
state["finished_at"]=stamp();save()
print(json.dumps({"status":state["status"],"identity_ok":all(state.get("identity_checks",{}).values()) if state.get("identity_checks") else False,"wb_write_attempts":state["wb_write_attempts"],"telegram_calls":0}))
