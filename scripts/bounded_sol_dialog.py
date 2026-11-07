"""Bounded stateless Sol calls. No tools, hidden history, automatic retries or WB access."""
import hashlib,json,os
from urllib.request import Request,urlopen
from datetime import datetime,timezone

MODEL='gpt-6.1-sol'
MAX_INPUT=12000
MAX_OUTPUT=1200
def stamp():return datetime.now(timezone.utc).isoformat()
def dump(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'),default=str)
def excerpt(v,n):
 s=dump(v)
 return v if len(s)<=n else {'coverage':'excerpt_only_not_complete','excerpt':s[:n],'original_chars':len(s)}
def compact_message(value):
 """Keep the question and scope; cap dated evidence explicitly rather than copy session history."""
 ctx=value.get('dated_work_context',{})
 priority=('analytics','data_request','telegram_reply_context','latest_hourly_snapshot','campaign_execution_registry','work_notes','recent_delivered_replies','china_catalogue')
 out={};remaining=18000
 for key in list(priority)+[k for k in ctx if k not in priority]:
  if key not in ctx or remaining<300:continue
  item=excerpt(ctx[key],min(remaining,7000 if key=='analytics' else 3000))
  size=len(dump(item));out[key]=item;remaining-=size
 return dump(dict(value,dated_work_context=out,evidence_scope='bounded; omitted/excerpted data is not proof of absence'))

class BoundedSol:
 def __init__(self,db,root,transport=None):self.db,self.root,self.transport=db,root,transport or self.http
 def key(self,identity):return self.root+'model-receipt:'+hashlib.sha256(identity.encode()).hexdigest()
 def http(self,path,body=None):
  req=Request('https://api.openai.com/v1/'+path,headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'],'Content-Type':'application/json'},data=None if body is None else dump(body).encode())
  with urlopen(req,timeout=100)as r:return json.load(r)
 def recover(self,identity):
  p=self.db.get(self.key(identity))or{}
  if p.get('status')=='completed' and p.get('text'):return p['text']
  raise RuntimeError('Prior model outcome unresolved; no automatic resubmission')
 def answer(self,identity,instructions,message):
  key=self.key(identity)
  if self.db.get(key):return self.recover(identity)
  if len(instructions)+len(message)>38000:raise ValueError('Context exceeds bounded dialogue size')
  body={'model':MODEL,'instructions':instructions,'input':message,'max_output_tokens':MAX_OUTPUT,'reasoning':{'effort':'low'},'store':False,'tools':[]}
  count=self.transport('responses/input_tokens',{'model':MODEL,'instructions':instructions,'input':message})
  if type(count.get('input_tokens'))is not int or not 0<count['input_tokens']<=MAX_INPUT:raise ValueError('Input token budget exceeded; no paid call')
  # Durable reservation before submission; uncertain outcomes never resubmitted.
  receipt={'status':'submitting_uncertain','identity':identity,'model':MODEL,'input_tokens_counted':count['input_tokens'],'max_output_tokens':MAX_OUTPUT,'submitted_at':stamp(),'model_retries':0,'history_mode':'stateless_bounded'}
  self.db.once(key,receipt)
  response=self.transport('responses',body)
  text=''.join(p.get('text','')for item in response.get('output',[])if item.get('type')=='message'for p in item.get('content',[])if p.get('type')=='output_text')
  usage=response.get('usage')or{}
  receipt.update(status='completed'if response.get('status')=='completed'and text else'provider_incomplete',response_id=response.get('id'),provider_model=response.get('model'),usage=usage,text=text,received_at=stamp())
  self.db.update(key,receipt)
  if receipt['status']!='completed':raise RuntimeError('Incomplete bounded model response; no retry')
  return text
