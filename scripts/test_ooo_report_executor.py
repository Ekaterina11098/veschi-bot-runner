import unittest,copy
try:import requests
except ModuleNotFoundError:
 import sys,types
 sys.modules['requests']=types.SimpleNamespace(RequestException=ConnectionError,request=lambda *a,**k:(_ for _ in()).throw(AssertionError('Live network forbidden in offline test')))
from datetime import datetime,timezone,timedelta
from ooo_report_executor import Executor,Deferred,Stop,validate,ROOT,CHAT,BOT,LEGACY
from ooo_report_command import approve,digest

class DB:
 def __init__(self):self.data={}
 def get(self,k):return copy.deepcopy(self.data.get(k))
 def update(self,k,v):self.data[k]=copy.deepcopy(v)
 def put(self,k,v):self.update(k,v)
 def once(self,k,v):
  if k in self.data:raise Stop('duplicate')
  self.update(k,v)
class Response:
 def __init__(self,status,data,headers=None):self.status_code=status;self.data=data;self.headers=headers or {};self.text=''
 def json(self):return copy.deepcopy(self.data)
def campaign():return {'id':39605581,'status':9,'currency':'KGS','bid_type':'manual','settings':{'placements':{'search':True,'recommendations':True},'payment_type':'cpc'},'restrictions':{'can_change_nms':True},'nm_settings':[{'nm_id':1,'subject':{'id':50},'bids_kopecks':{'search':360,'recommendations':325}},{'nm_id':2,'subject':{'id':50},'bids_kopecks':{'search':325,'recommendations':325}}]}
class Flow(unittest.TestCase):
 def setUp(self):
  self.db=DB();self.c=campaign();self.calls=[]
  self.m={'cabinet':'token_1','currency':'KGS','actions':[{'cid':39605581,'nm':1,'kind':'reduce_bid','placement':'search','from_minor':360,'to_minor':325}],'topups':[],'other_changes':[]}
  self.exp=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
  self.binding={'status':'delivered_verified','chat_id':CHAT,'manifest':self.m,'manifest_sha256':digest(self.m),'plan_id':'test','expires_at':self.exp}
  self.db.data[ROOT+'report_execution_policy']={'enabled':True}
  self.db.data[ROOT+'report_binding:'+str(CHAT)+':4']=self.binding
  self.msg={'text':'Сделай всё','message_id':8,'from':{'id':123},'chat':{'id':CHAT},'reply_to_message':{'message_id':4,'from':{'id':BOT}}}
 def request(self,method,url,**kw):
  path=url.split('.ru')[1];self.calls.append((method,path,kw))
  if path.endswith('/adverts'):return Response(200,{'adverts':[self.c]})
  if path.endswith('/bids'):
   self.c['nm_settings'][0]['bids_kopecks']['search']=325;return Response(200,{'bids':kw['json']['bids']})
  if path.endswith('/config'):return Response(200,{'currency':'KGS','minTopUp':100000})
  raise AssertionError(path)
 def approved(self):
  result=approve(self.db,self.msg,ROOT,CHAT,BOT,membership={'status':'member','user':{'id':123}})
  self.assertEqual(result['status'],'approved_pending_execution');return result['approval_key']
 def test_member_to_execution_and_duplicate(self):
  key=self.approved();a=self.db.get(key);x=Executor(self.db,'test',self.request);x.process(key,a)
  self.assertEqual(self.db.get(key)['status'],'verified')
  self.assertEqual(approve(self.db,self.msg,ROOT,CHAT,BOT,membership={'status':'member','user':{'id':123}})['status'],'existing')
  self.assertEqual(sum(m=='PATCH'for m,_,_ in self.calls),1)
 def test_accepted_write_survives_readback_429(self):
  key=self.approved();x=Executor(self.db,'test',self.request);original=self.request;count=[0]
  def request(method,url,**kw):
   if url.endswith('/adverts'):
    count[0]+=1
    if count[0]==2:return Response(429,{'error':'rate limit'},{'Retry-After':'1'})
   return original(method,url,**kw)
  x.request=request;x.process(key,self.db.get(key));self.assertEqual(self.db.get(key)['status'],'waiting_shared_quota')
  self.db.data={k:v for k,v in self.db.data.items()if not k.startswith('wb-pause:')}
  x.process(key,self.db.get(key));self.assertEqual(self.db.get(key)['status'],'verified');self.assertEqual(sum(m=='PATCH'for m,_,_ in self.calls),1)
 def test_unknown_write_is_never_replayed(self):
  key=self.approved();x=Executor(self.db,'test',self.request);a=self.db.get(key);a['execution']={'steps':{'bids':{'status':'submitting'}},'expected':{'39605581':self.c},'members':{},'bids':{'39605581':[{}]},'statuses':[]};self.db.update(key,a)
  x.process(key,a);self.assertEqual(self.db.get(key)['status'],'attention');self.assertEqual(self.calls,[])
 def test_minimum_never_rounds_up(self):
  x=Executor(self.db,'test',self.request);s={};xsave=lambda:None
  with self.assertRaisesRegex(Stop,'below provider minimum'):x.fund(s,xsave,{'cid':39605581,'amount_kgs':500},'deposit')
  self.assertFalse(any(p.endswith('/deposit')for _,p,_ in self.calls))
 def test_nonmember_and_unbound(self):
  self.assertEqual(approve(self.db,self.msg,ROOT,CHAT,BOT,membership={'status':'left','user':{'id':123}})['status'],'rejected')
  self.msg['reply_to_message']['message_id']=99
  self.assertEqual(approve(self.db,self.msg,ROOT,CHAT,BOT,membership={'status':'member','user':{'id':123}})['status'],'unbound')
 def test_tampered_and_expired(self):
  self.binding['manifest_sha256']='bad'
  self.assertEqual(approve(self.db,self.msg,ROOT,CHAT,BOT,membership={'status':'member','user':{'id':123}})['status'],'unbound')
  self.binding['manifest_sha256']=digest(self.m);self.binding['expires_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
  self.assertEqual(approve(self.db,self.msg,ROOT,CHAT,BOT,membership={'status':'member','user':{'id':123}})['status'],'expired')
 def test_explicitly_rejected_error_body_retained(self):
  x=Executor(self.db,'test',lambda *a,**kw:Response(400,{'error':'minimum deposit amount is 1000'}));s={}
  with self.assertRaises(Stop):x.call(s,lambda:None,'POST','/adv/v1/budget/deposit',{'sum':500,'type':1},step='deposit')
  self.assertEqual(s['steps']['deposit']['status'],'rejected');self.assertIn('1000',s['steps']['deposit']['response']['error'])
  with self.assertRaisesRegex(Stop,'no replay'):x.call(s,lambda:None,'POST','/adv/v1/budget/deposit',step='deposit')
 def test_funding_only_and_forbidden_campaign(self):
  m=copy.deepcopy(self.m);m['actions']=[];m['topups']=[{'cid':39605581,'amount_kgs':500}];validate(m)
  m['topups'][0]['cid']=41517533
  with self.assertRaises(Stop):validate(m)

if __name__=='__main__':unittest.main()

