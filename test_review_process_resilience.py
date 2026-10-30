import base64,json,sys,unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_approval_process import acquire_ui_lock
from review_ciphertext_archive import archive,blob_sha,ArchiveTransient
def ciphertext():
 return json.dumps(dict(format='owner-rsa-aesgcm-v1',wrapped_key=base64.b64encode(b'k'*256).decode(),nonce=base64.b64encode(b'n'*12).decode(),ciphertext=base64.b64encode(b'c'*32).decode(),plaintext_sha256='a'*64)).encode()
class LockTests(unittest.TestCase):
 def test_contention_uses_short_queries_then_acquires(self):
  conn=Mock();conn.execute.return_value.fetchone.side_effect=[(False,),(False,),(True,)]
  clock=Mock(side_effect=[0,1,2]);sleep=Mock()
  self.assertTrue(acquire_ui_lock(conn,clock=clock,sleep=sleep))
  self.assertEqual(conn.execute.call_count,3)
  self.assertTrue(all('pg_try_advisory_lock' in c.args[0] for c in conn.execute.call_args_list))
  self.assertEqual(sleep.call_count,2)
 def test_busy_deadline_returns_without_processing(self):
  conn=Mock();conn.execute.return_value.fetchone.return_value=(False,)
  self.assertFalse(acquire_ui_lock(conn,wait_seconds=2,clock=Mock(side_effect=[0,1,2]),sleep=Mock()))
  self.assertEqual(conn.execute.call_count,2)
class ArchiveTests(unittest.TestCase):
 def test_unknown_put_success_is_reconciled_without_second_put(self):
  raw=ciphertext();saved=False;posts=[]
  def request(method,url,body):
   nonlocal saved
   if method=='GET':return (200,{'sha':blob_sha(raw)}) if saved else (404,{})
   posts.append(body);saved=True;raise TimeoutError()
  result=archive(raw,'owner/repo','123',request,sleep=Mock())
  self.assertEqual(result['status'],'confirmed');self.assertEqual(len(posts),1)
 def test_transient_failures_retry_only_same_ciphertext(self):
  raw=ciphertext();puts=[];reads=0;saved=False
  def request(method,url,body):
   nonlocal reads,saved
   if method=='GET':
    reads+=1
    if reads==1:raise ArchiveTransient()
    return (200,{'sha':blob_sha(raw)}) if saved else (404,{})
   puts.append(body['content'])
   if len(puts)==1:raise ArchiveTransient()
   saved=True;return 201,{}
  self.assertEqual(archive(raw,'owner/repo','123',request,sleep=Mock())['status'],'confirmed')
  self.assertEqual(len(set(puts)),1);self.assertEqual(base64.b64decode(puts[0]),raw)
 def test_existing_identical_file_needs_no_write(self):
  raw=ciphertext();request=Mock(return_value=(200,{'sha':blob_sha(raw)}))
  self.assertTrue(archive(raw,'owner/repo','123',request)['already_present'])
  self.assertEqual(request.call_count,1)
 def test_collision_does_not_overwrite(self):
  request=Mock(return_value=(200,{'sha':'other'}))
  with self.assertRaises(ValueError):archive(ciphertext(),'owner/repo','123',request)
  self.assertEqual(request.call_count,1)
 def test_exhaustion_stays_bounded(self):
  request=Mock(side_effect=ArchiveTransient())
  with self.assertRaises(ArchiveTransient):archive(ciphertext(),'owner/repo','123',request,sleep=Mock(),attempts=3)
  self.assertEqual(request.call_count,3)
 def test_reject_plaintext_before_network(self):
  request=Mock()
  with self.assertRaises(ValueError):archive(b'{"customer":"private"}','owner/repo','123',request)
  request.assert_not_called()
class BusyMainTests(unittest.TestCase):
 def test_busy_backed_update_and_unqueued_dispatch(self):
  import os,tempfile
  from types import SimpleNamespace
  from unittest.mock import patch
  import review_approval_process as process
  import review_approval_inbox as inbox
  for backed in (True,False):
   with self.subTest(backed=backed),tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
    conn=Mock();conn.execute.return_value.fetchone.return_value=(1,) if backed else None
    env=dict(REVIEW_APPROVAL_ENABLED='1',REVIEW_APPROVAL_DSN='test',REVIEW_APPROVAL_INGRESS_KEY='test',REVIEW_APPROVAL_OWNER_ID='owner',TELEGRAM_ALLOWED_CHAT_ID='chat',REVIEW_APPROVAL_BOT_ID='bot',RUNNER_TEMP=tmp,RECOVERY_PUBLIC_KEY='test',SEALED_UPDATE='encrypted')
    with patch.dict(os.environ,env),patch.dict(sys.modules,{'psycopg':SimpleNamespace(connect=Mock(return_value=conn)),'wildberries':Mock()}),patch.object(process,'Approval'),patch.object(process,'Repository'),patch.object(process,'DurableBridge'),patch.object(process,'snapshot'),patch.object(process,'encrypt',return_value={'encrypted':True}),patch.object(process,'decrypt_update',return_value={'update_id':123}),patch.object(process,'acquire_ui_lock',return_value=False),patch.object(inbox,'drain') as drain,patch.object(inbox,'process_update') as one:
     if backed:process.main()
     else:
      with self.assertRaises(process.ApprovalLockBusy):process.main()
     drain.assert_not_called();one.assert_not_called();conn.close.assert_called_once()
     self.assertTrue((Path(tmp)/'review-approval-output'/'approval-supplement.aes.json').is_file())
if __name__=='__main__':unittest.main()
