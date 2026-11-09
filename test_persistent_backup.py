import contextlib,hashlib,json,tempfile,unittest
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_approval_backup import IncrementalSnapshot,TABLES

class Result:
    def __init__(self,rows):self.rows=rows
    def fetchall(self):return self.rows
    def fetchone(self):return self.rows[0]

class Connection:
    def __init__(self):
        self.data={t:{} for t in TABLES+('source_cache','source_journal')}
        self.data['events']={'a':{'text':'large'*10000},'b':{'text':'delete'}}
        self.payload_reads=0;self.fail=False
    def transaction(self):return contextlib.nullcontext()
    def execute(self,sql,args=()):
        if sql.startswith('SET'):return Result([])
        if 'pg_current_snapshot' in sql:return Result([('snapshot','time')])
        table=sql.split('review_approval.')[1].split()[0]
        versions={k:hashlib.md5(json.dumps(v).encode()).hexdigest() for k,v in self.data[table].items()}
        if sql.startswith('SELECT md5(coalesce'):return Result([(str(sorted(versions.items())),)])
        if sql.startswith('SELECT id,md5') or sql.startswith('SELECT cache_key,md5') or sql.startswith('SELECT feedback_id,md5'):return Result(list(versions.items()))
        self.payload_reads+=1
        if self.fail:raise RuntimeError('read failure')
        return Result([(k,json.dumps(self.data[table][k])) for k in args[0]])

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).parent);self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'state.aes';self.conn=Connection();self.repo=SimpleNamespace(pg=True,conn=self.conn)
    def backup(self,secret=b'synthetic-secret',scope='project:token_1'):
        return IncrementalSnapshot(self.repo,self.path,secret,scope)
    def test_restart_reuses_payload_and_reconciles_changes_deletes(self):
        first=self.backup();a=first.capture();first.save_cache()
        self.assertNotIn(b'large',self.path.read_bytes())
        self.conn.payload_reads=0;second=self.backup();self.assertEqual(second.cache_status,'restored')
        self.assertEqual(second.capture()['manifest'],a['manifest']);self.assertEqual(self.conn.payload_reads,0)
        self.conn.data['events']['a']={'changed':True};del self.conn.data['events']['b'];self.conn.data['events']['c']={'new':True}
        second=self.backup();updated=second.capture()
        self.assertEqual(updated['tables'],IncrementalSnapshot(self.repo).capture()['tables'])
    def test_corruption_wrong_key_and_scope_fall_back_complete(self):
        b=self.backup();expected=b.capture();b.save_cache()
        for secret,scope in [(b'wrong','project:token_1'),(b'synthetic-secret','project:token_2')]:
            c=self.backup(secret,scope);self.assertEqual(c.cache_status,'cold');self.assertEqual(c.capture()['tables'],expected['tables'])
        self.path.write_bytes(b'broken');c=self.backup();self.assertEqual(c.capture()['tables'],expected['tables'])
    def test_failed_capture_does_not_replace_last_good_cache(self):
        b=self.backup();b.capture();b.save_cache();old=self.path.read_bytes()
        self.conn.data['events']['new']={'value':True};self.conn.fail=True
        with self.assertRaises(RuntimeError):self.backup().capture()
        self.assertEqual(self.path.read_bytes(),old)

if __name__=='__main__':unittest.main()
