"""Resolve the verified content-group destination before an existing stock job."""
import os,sys,runpy,hmac,hashlib
from pathlib import Path
import psycopg
root=os.environ['SUPABASE_SECRET_KEY'].encode()
password=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
with psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=password,sslmode='require',connect_timeout=15) as conn:
 row=conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:content-group:v1'").fetchone()
 if not row or row[0].get('enabled') is not True or row[0].get('destination_verified') is not True:raise RuntimeError('Verified content group is required; private delivery forbidden')
 os.environ['TELEGRAM_ALLOWED_CHAT_ID']=str(row[0]['chat_id'])
target=Path(sys.argv[1]).resolve();sys.path.insert(0,str(target.parent));runpy.run_path(str(target),run_name='__main__')
