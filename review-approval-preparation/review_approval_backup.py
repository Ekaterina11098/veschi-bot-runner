"""Consistent supplement, authenticated encryption; no plaintext writes to artifacts."""
import base64,json,hashlib,secrets,os
from review_telegram_approval import sha

TABLES=('items','cards','events','intents')
def snapshot(repo):
    # Separate connection, idle before invocation. Repeatable-read binds every table.
    with repo.conn.transaction():
        repo.conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        data={table:[{'id':key,'payload':json.loads(payload)} for key,payload in
            repo.execute('SELECT id,payload FROM {p}'+table+' ORDER BY id').fetchall()] for table in TABLES}
        data['source_cache']=[{'cache_key':key,'payload':payload,'updated_at':str(stamp)} for key,payload,stamp in
            repo.conn.execute("SELECT cache_key,payload,updated_at FROM review_approval.source_cache WHERE starts_with(cache_key,'reviews:') ORDER BY cache_key").fetchall()]
        data['source_journal']=[{'feedback_id':key,'state':state,'error':error} for key,state,error in
            repo.conn.execute('SELECT feedback_id,state,error FROM review_approval.source_journal ORDER BY feedback_id').fetchall()]
        point=repo.conn.execute('SELECT pg_current_snapshot()::text,transaction_timestamp()::text').fetchone()
    return dict(format='review-approval-supplement-v1',point=list(point),tables=data,code_commit=os.getenv('GITHUB_SHA','isolated-test'),private_wb_commit='1b4201067880e379d8dacbe5f6ca3f9848d6ffb0',
        manifest={key:{'count':len(rows),'sha256':sha(rows)} for key,rows in data.items()})

def validate(data):
    if data.get('format')!='review-approval-supplement-v1':raise ValueError('Backup format')
    if set(data['tables'])!=set(TABLES+('source_cache','source_journal')):raise ValueError('Backup composition')
    for table,rows in data['tables'].items():
        if data['manifest'].get(table)!={'count':len(rows),'sha256':sha(rows)}:raise ValueError('Manifest mismatch')
    return data

def encrypt(data,public_pem):
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    validate(data);raw=json.dumps(data,ensure_ascii=False,sort_keys=True).encode();key=secrets.token_bytes(32);nonce=secrets.token_bytes(12)
    b=lambda x:base64.b64encode(x).decode()
    return dict(format='owner-rsa-aesgcm-v1',wrapped_key=b(load_pem_public_key(public_pem).encrypt(key,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))),nonce=b(nonce),ciphertext=b(AESGCM(key).encrypt(nonce,raw,None)),plaintext_sha256=hashlib.sha256(raw).hexdigest())

def decrypt(envelope,private_key):
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    b=base64.b64decode
    key=private_key.decrypt(b(envelope['wrapped_key']),padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
    raw=AESGCM(key).decrypt(b(envelope['nonce']),b(envelope['ciphertext']),None)
    if hashlib.sha256(raw).hexdigest()!=envelope['plaintext_sha256']:raise ValueError('Plaintext checksum')
    return validate(json.loads(raw))

def restore_empty(repo,data):
    validate(data)
    with repo.transaction():
        if any(repo.count(table) for table in TABLES):raise ValueError('Restore only into empty isolated approval schema')
        for table in TABLES:
            for row in data['tables'][table]:repo.put(table,row['id'],row['payload'])
    for table in TABLES:
        actual=[{'id':key,'payload':json.loads(payload)} for key,payload in repo.execute('SELECT id,payload FROM {p}'+table+' ORDER BY id').fetchall()]
        if sha(actual)!=data['manifest'][table]['sha256']:raise ValueError('Restore readback mismatch')
    return True


