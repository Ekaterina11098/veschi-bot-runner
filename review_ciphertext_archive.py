"""Archive existing ciphertext only; never import or execute approval/publication."""
import base64,hashlib,json,os,re,time,urllib.request,urllib.error
from pathlib import Path

class ArchiveTransient(Exception):pass
def validate_ciphertext(raw):
    if len(raw)>90*1024*1024:raise ValueError('Ciphertext exceeds archive limit')
    obj=json.loads(raw)
    if set(obj)!={'format','wrapped_key','nonce','ciphertext','plaintext_sha256'} or obj['format']!='owner-rsa-aesgcm-v1':raise ValueError('Only owner ciphertext can be archived')
    if len(base64.b64decode(obj['nonce'],validate=True))!=12 or len(base64.b64decode(obj['wrapped_key'],validate=True))<128 or len(base64.b64decode(obj['ciphertext'],validate=True))<16 or not re.fullmatch('[0-9a-f]{64}',obj['plaintext_sha256']):raise ValueError('Invalid ciphertext envelope')
def blob_sha(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
def archive(raw,repository,run_id,request,sleep=time.sleep,attempts=6):
    validate_ciphertext(raw)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository) or not str(run_id).isdigit():raise ValueError('Invalid archive destination')
    digest=hashlib.sha256(raw).hexdigest()
    path='recovery-output/review-approval/approval-'+str(run_id)+'-'+digest[:16]+'.aes.json'
    url='https://api.github.com/repos/'+repository+'/contents/'+path
    expected=blob_sha(raw)
    payload={'message':'Preserve encrypted review approval supplement','content':base64.b64encode(raw).decode(),'branch':'main'}
    for attempt in range(attempts):
        try:
            # This metadata read also reconciles an unknown previous PUT outcome.
            status,data=request('GET',url+'?ref=main',None)
            if status==200:
                if data.get('sha')!=expected:raise ValueError('Archive content collision')
                return {'status':'confirmed','path':path,'sha256':digest,'already_present':True}
            if status!=404:raise ArchiveTransient('Archive metadata unavailable')
            status,data=request('PUT',url,payload)
            if status not in (200,201):raise ArchiveTransient('Archive write unconfirmed')
            # Read back even after an accepted write. A retry never replays business actions.
            status,data=request('GET',url+'?ref=main',None)
            if status==200 and data.get('sha')==expected:
                return {'status':'confirmed','path':path,'sha256':digest,'already_present':False}
            raise ArchiveTransient('Archive readback not confirmed')
        except (ArchiveTransient,TimeoutError,ConnectionError,urllib.error.URLError):
            if attempt+1==attempts:raise ArchiveTransient('Ciphertext archive retries exhausted') from None
            sleep(min(30,2**(attempt+1)))
    raise AssertionError('Unreachable')
def main():
    target=Path(os.environ['RUNNER_TEMP'])/'review-approval-output'/'approval-supplement.aes.json'
    if not target.is_file():
        print(json.dumps({'archive':'not_available','reason':'No ciphertext was produced; decision processing is not replayed'}));return
    raw=target.read_bytes()
    token=os.environ['GH_TOKEN']
    def request(method,url,payload):
        headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
        body=None if payload is None else json.dumps(payload).encode()
        if body is not None:headers['Content-Type']='application/json'
        req=urllib.request.Request(url,data=body,headers=headers,method=method)
        try:
            with urllib.request.urlopen(req,timeout=45) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code==404:return 404,{}
            if exc.code in (409,422,429,500,502,503,504) or (exc.code==403 and (exc.headers.get('Retry-After') or exc.headers.get('X-RateLimit-Remaining')=='0')):
                raise ArchiveTransient('Archive HTTP '+str(exc.code)) from None
            raise RuntimeError('Archive denied HTTP '+str(exc.code)) from None
    result=archive(raw,os.environ['GITHUB_REPOSITORY'],os.environ['GITHUB_RUN_ID'],request)
    (target.parent/'archive-receipt.json').write_text(json.dumps(result),encoding='utf-8')
    print(json.dumps(result))
if __name__=='__main__':main()
