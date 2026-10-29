import os,copy,unittest,types
from unittest.mock import patch
import china_minimum_server_wb_read29 as m
class Fake:
 data={}
 def get(self,k):return copy.deepcopy(self.data.get(k))
 def put(self,k,v):self.data[k]=copy.deepcopy(v)
 def create(self,k,v):
  if k in self.data:return False
  self.put(k,v);return True
class Checks(unittest.TestCase):
 def setUp(self):
  Fake.data={m.CONFIG:dict(profile_id='p',seller_name='VESCHI LIMITED',seller_ui_id=250184767,currency='CNY'),'china_agent:prices:v1':{'rows':[{'nmID':1473244991,'vendorCode':'sample'}]}}
 def execute(self,post,get):
  with patch.dict(os.environ,{'GITHUB_REPOSITORY':'Ekaterina11098/veschi-bot-runner','GITHUB_REF':'refs/heads/main','TINYFISH_API_KEY':'offline'}),patch.object(m,'Cache',Fake),patch.object(m.requests,'post',post,create=True),patch.object(m.requests,'get',get,create=True):m.main()
 def ok(self,data):return types.SimpleNamespace(ok=True,json=lambda:data)
 def result(self,seller='VESCHI LIMITED'):
  return self.ok({'status':'COMPLETED','result':dict(seller_name=seller,seller_ui_id='250184767',currency='CNY',article='sample',nm_id='1473244991',seller_price_with_discount='192.72',minimum_price='192',error='')})
 def test_one_submission_even_after_completed_replay(self):
  calls=[]
  def post(*a,**kw):
   calls.append(kw['json']);return self.ok({'run_id':'read1'})
  self.execute(post,lambda *a,**kw:self.result())
  self.execute(post,lambda *a,**kw:(_ for _ in ()).throw(AssertionError('Replay')))
  self.assertEqual(len(calls),1);self.assertEqual(Fake.data[m.ROOT]['status'],'verified_read')
  self.assertTrue(calls[0]['use_profile']);self.assertFalse(Fake.data[m.ROOT]['minimum_writer_enabled']);self.assertEqual(Fake.data[m.ROOT]['wb_writes'],0)
 def test_uncertain_submission_is_never_repeated(self):
  count=[]
  def fail(*a,**kw):count.append(1);raise m.requests.RequestException()
  with self.assertRaises(RuntimeError):self.execute(fail,None)
  self.execute(fail,None);self.assertEqual(len(count),1);self.assertEqual(Fake.data[m.ROOT]['status'],'uncertain_submitting')
 def test_wrong_seller_not_verified(self):
  self.execute(lambda *a,**kw:self.ok({'run_id':'read1'}),lambda *a,**kw:self.result('OTHER'))
  self.assertEqual(Fake.data[m.ROOT]['status'],'failed')
if __name__=='__main__':unittest.main()
