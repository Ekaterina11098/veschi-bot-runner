"""Restricted stock deployment support; no Telegram or business queue dispatcher."""
import os,json,hashlib,hmac,base64,secrets,traceback,time
from pathlib import Path
ROLE='stock_executor_20261015'
PROJECT='abxgjoqlddhtcmjcjwxw'
HOST='aws-0-eu-central-1.pooler.supabase.com'
ROOT=Path(os.environ['RUNNER_TEMP'])
OUT=ROOT/'stock-deploy-proof'
OUT.mkdir(exist_ok=True)
OWNER_PUBLIC="-----BEGIN PUBLIC KEY-----\nMIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEAst6VhelAueCkrgeGYeMm\nBBn16lRh8KaLjidOXiKiAtzBSRvtvGpcz4JsdOtfs4zi0CHAcs60iD4Kdh+UlJMm\n0z8ekieLrY4DWqmuXyRH63TYGQyqOS+O5gtHpEXo6aHZSW6IooPJC2/rI5NtAVFr\nTV76dCAE+8cQXQGKUerWcRQ1Amb4s5gWcDzg81R9VwhDJgDyttlrlvkmY5BWWjqy\nVCJnrMPgwKVDaoh5KMAHH+O5AZJuGOrjC1exbJ4N7UkglOgGvWGllIeaRNttuPSV\nLmn5epyhasMfeVXyYaVqgoQcDfIexkTWgESr8+xPk663tr5OTbbfYEkWKordC7AD\nyUe9aT73GMnk0rXwCZzGKpw3rOukkHn40CUJPK7NLmSwE5RwSCuyxHpF+WutDzl6\n6ZCXZhgzYh9brD/hvbB6q7xoPxweqfD+71ONlf8WC1S3dWDo8sCKGWToqLncFce8\neAI8KPT+ymfjEqA3/sGKw1z/FkKvcuCMZpfHlTBFbdJjAgMBAAE=\n-----END PUBLIC KEY-----\n"
def password():
    return hmac.new(os.environ['SUPABASE_SECRET_KEY'].encode(),b'veschi:stock-executor:20261015:v1',hashlib.sha256).hexdigest()
def runtime_db():
    import psycopg
    return psycopg.connect(host=HOST,port=5432,dbname='postgres',user=ROLE+'.'+PROJECT,password=password(),sslmode='require',connect_timeout=15,options='-c search_path=stock_execution,pg_catalog -c statement_timeout=30000',application_name='owner_stock_controlled_20261015')
def seal(name,value):
    from cryptography.hazmat.primitives import serialization,hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key=secrets.token_bytes(32);nonce=secrets.token_bytes(12)
    public=serialization.load_pem_public_key(OWNER_PUBLIC.encode())
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,default=str).encode()
    encrypted=AESGCM(key).encrypt(nonce,raw,None)
    b=lambda x:base64.b64encode(x).decode()
    envelope=dict(format='owner-rsa-aesgcm-v1',wrapped_key=b(public.encrypt(key,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))),nonce=b(nonce),ciphertext=b(encrypted),plaintext_sha256=hashlib.sha256(raw).hexdigest())
    path=OUT/(name+'.aes.json');path.write_text(json.dumps(envelope))
    return path
def error(exc):
    text=''.join(traceback.format_exception(exc))
    for name,value in os.environ.items():
        if len(value)>5 and any(x in name for x in ('TOKEN','PASSWORD','SECRET','DATABASE_URL')):text=text.replace(value,'[redacted]')
    return dict(type=type(exc).__name__,trace=text)
