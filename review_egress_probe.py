"""Owner-requested read-only production probe. No marketplace or Telegram clients."""
import os,sys,json,hmac,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_telegram_approval import Repository
from review_approval_backup import IncrementalSnapshot,validate

class MeasuredCursor:
    def __init__(self,c,m):self.c=c;self.m=m
    def fetchall(self):
        rows=self.c.fetchall();self.m.bytes+=len(json.dumps(rows,default=str).encode());return rows
    def fetchone(self):
        row=self.c.fetchone();self.m.bytes+=len(json.dumps(row,default=str).encode());return row
class MeasuredConnection:
    def __init__(self,c):self.c=c;self.bytes=0
    def transaction(self):return self.c.transaction()
    def execute(self,sql,args=()):return MeasuredCursor(self.c.execute(sql,args),self)

def main():
    import psycopg
    root=os.environ['SUPABASE_SECRET_KEY'].encode()
    pw=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
    with psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=pw,sslmode='require',autocommit=True,connect_timeout=15,options='-c default_transaction_read_only=on -c statement_timeout=30000') as conn:
        repo=Repository(conn,postgres=True);m=MeasuredConnection(conn);repo.conn=m
        b=IncrementalSnapshot(repo);first=b.capture();validate(first);initial=m.bytes
        m.bytes=0;second=b.capture();validate(second)
        result=dict(code_commit=os.getenv('GITHUB_SHA'),first_capture_bytes=initial,second_capture_bytes=m.bytes,table_counts={k:len(v) for k,v in second['tables'].items()},same_manifest=first['manifest']==second['manifest'],measurement='decoded SQL response bytes estimate; not provider billing',wb_calls=0,telegram_calls=0,database_writes=0)
        if result['same_manifest'] and m.bytes>=initial/100:raise RuntimeError('Unchanged backup did not reduce transfer')
        print(json.dumps(result))
if __name__=='__main__':main()
