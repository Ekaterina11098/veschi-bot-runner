"""Consistent supplement, authenticated encryption; no plaintext writes to artifacts."""
import base64,json,hashlib,secrets,os
from review_telegram_approval import sha

TABLES=('items','cards','events','intents')
class IncrementalSnapshot:
    """Keep the full encrypted artifact, transfer only changed rows from Postgres.

    Each capture is still a single repeatable-read snapshot. Table fingerprints
    and row xmin versions are computed by Postgres; deletions are reconciled.
    Publish the local cache only after all reads complete, so failures are retryable.
    """
    def __init__(self,repo,cache_path=None,cache_secret=None,cache_scope=None):
        self.repo=repo;self.cache={};self.signatures={}
        self.cache_path=cache_path;self.cache_secret=cache_secret;self.cache_scope=cache_scope
        self.cache_status='disabled' if not cache_path else 'cold'
        if cache_path and cache_secret and cache_scope:
            try:
                from pathlib import Path
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                raw=Path(cache_path).read_bytes()
                state=json.loads(AESGCM(self._cache_key()).decrypt(raw[:12],raw[12:],cache_scope.encode()))
                if state['format']!='incremental-cache-v1':raise ValueError('Cache format')
                cache={t:{k:(v,row) for k,v,row in entries} for t,entries in state['tables'].items()}
                if set(cache)!=set(TABLES+('source_cache','source_journal')):raise ValueError('Cache composition')
                if any(len(cache[t])!=len(state['tables'][t]) for t in cache):raise ValueError('Duplicate cache identity')
                if sha(state['tables'])!=state['digest']:raise ValueError('Cache digest')
                self.cache=cache;self.cache_status='restored'
                # Never trust a cached signature across database/process lifetimes.
                # Re-read versions, including deletes; cached payload is only reused
                # for matching content hashes (not potentially recycled xmin).
            except Exception:
                self.cache={};self.signatures={};self.cache_status='cold'

    def _cache_key(self):
        import hmac
        return hmac.new(self.cache_secret,b'veschi:encrypted-backup-cache:v1',hashlib.sha256).digest()

    def save_cache(self):
        if not (self.cache_path and self.cache_secret and self.cache_scope):return
        from pathlib import Path
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        tables={t:[[k,v,row] for k,(v,row) in entries.items()] for t,entries in self.cache.items()}
        state={'format':'incremental-cache-v1','tables':tables,'digest':sha(tables)}
        nonce=secrets.token_bytes(12)
        encrypted=nonce+AESGCM(self._cache_key()).encrypt(nonce,json.dumps(state,ensure_ascii=False).encode(),self.cache_scope.encode())
        target=Path(self.cache_path);target.parent.mkdir(parents=True,exist_ok=True)
        temp=target.with_suffix('.tmp');temp.write_bytes(encrypted);os.chmod(temp,0o600);os.replace(temp,target)

    def capture(self):
        repo=self.repo
        if not repo.pg:return snapshot(repo)
        tables={};next_cache={};signatures={}
        with repo.conn.transaction():
            repo.conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            for table in TABLES+('source_cache','source_journal'):
                key='cache_key' if table=='source_cache' else 'feedback_id' if table=='source_journal' else 'id'
                where=" WHERE starts_with(cache_key,'reviews:')" if table=='source_cache' else ''
                base='review_approval.'+table
                # Views do not expose xmin. Hash only their declared columns on
                # the server; this also detects deletes and same-timestamp edits.
                version="md5(payload::text||coalesce(updated_at::text,''))" if table=='source_cache' else "md5(jsonb_build_array(state,error)::text)" if table=='source_journal' else 'md5(payload::text)'
                signature=repo.conn.execute("SELECT md5(coalesce(string_agg("+key+"::text||':'||"+version+",',' ORDER BY "+key+"),'')) FROM "+base+where).fetchone()[0]
                signatures[table]=signature
                old=self.cache.get(table,{})
                if self.signatures.get(table)==signature:
                    rows=old
                else:
                    versions=dict(repo.conn.execute('SELECT '+key+','+version+' FROM '+base+where).fetchall())
                    changed=[k for k,v in versions.items() if k not in old or old[k][0]!=v]
                    rows={k:old[k] for k in versions if k not in changed}
                    fields='cache_key,payload,updated_at' if table=='source_cache' else 'feedback_id,state,error' if table=='source_journal' else 'id,payload'
                    for offset in range(0,len(changed),250):
                        for raw in repo.conn.execute('SELECT '+fields+' FROM '+base+' WHERE '+key+'=ANY(%s) ORDER BY '+key,(changed[offset:offset+250],)).fetchall():
                            k=raw[0]
                            value=({'cache_key':k,'payload':raw[1],'updated_at':str(raw[2])} if table=='source_cache' else {'feedback_id':k,'state':raw[1],'error':raw[2]} if table=='source_journal' else {'id':k,'payload':json.loads(raw[1])})
                            rows[k]=(versions[k],value)
                    if set(rows)!=set(versions):raise ValueError('Incomplete incremental backup read')
                next_cache[table]=rows
                tables[table]=[rows[k][1] for k in sorted(rows)]
            point=repo.conn.execute('SELECT pg_current_snapshot()::text,transaction_timestamp()::text').fetchone()
        result=dict(format='review-approval-supplement-v1',point=list(point),tables=tables,code_commit=os.getenv('GITHUB_SHA','isolated-test'),private_wb_commit='1b4201067880e379d8dacbe5f6ca3f9848d6ffb0',manifest={k:{'count':len(v),'sha256':sha(v)} for k,v in tables.items()})
        validate(result)
        self.cache=next_cache;self.signatures=signatures
        return result

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



