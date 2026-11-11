"""Event-driven Codex app-server transport. Native threads and tool loop, no polling."""
import asyncio,base64,gzip,hashlib,json,os,re,tempfile,time
from pathlib import Path
from datetime import datetime,timezone
ROOT='china_agent:codex_appserver:v1:'
def stamp():return datetime.now(timezone.utc).isoformat()
def encode(data):return base64.b64encode(gzip.compress(data)).decode()
def decode(text):return gzip.decompress(base64.b64decode(text,validate=True))
def restore_rollout(state,specs):
 raw=decode(state['rollout_gzip_b64'])
 if hashlib.sha256(raw).hexdigest()!=state['rollout_sha256']:raise ValueError('Native thread integrity mismatch')
 lines=raw.splitlines(keepends=True)
 if not lines:raise ValueError('Native thread metadata missing')
 meta=json.loads(lines[0])
 if meta.get('type')!='session_meta'or meta.get('payload',{}).get('id')!=state['thread_id']:raise ValueError('Native thread metadata identity mismatch')
 # This pinned protocol restores tool definitions from rollout metadata. Refresh
 # only that registry; preserve every historical turn byte-for-byte.
 meta['payload']['dynamic_tools']=specs
 lines[0]=(json.dumps(meta,ensure_ascii=False,separators=(',',':'))+'\n').encode()
 return b''.join(lines)
class Client:
 def __init__(self,tool,home,model):self.tool=tool;self.home=Path(home);self.model=model;self.seq=0;self.waiters={};self.finished=None;self.final=[];self.calls=[]
 async def start(self):
  self.home.mkdir(parents=True,exist_ok=True)
  env={k:v for k,v in os.environ.items()if k in ('PATH','HOME','TMPDIR','TEMP','TMP','SYSTEMROOT','WINDIR','OPENAI_API_KEY','SSL_CERT_FILE','HTTPS_PROXY','HTTP_PROXY','NO_PROXY')}
  env['CODEX_HOME']=str(self.home)
  self.log=open(self.home/'transport.log','w',encoding='utf-8')
  self.proc=await asyncio.create_subprocess_exec('codex','app-server','--listen','stdio://','-c','features.shell_tool=false','-c','features.unified_exec=false','-c','features.multi_agent=false','-c','web_search="disabled"',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=self.log,env=env)
  self.reader=asyncio.create_task(self.read())
  await self.rpc('initialize',{'clientInfo':{'name':'veschi_telegram_codex','title':'VESCHI Telegram Codex','version':'1.0.0'},'capabilities':{'experimentalApi':True}})
  await self.send({'method':'initialized','params':{}})
  if os.environ.get('OPENAI_API_KEY'):await self.rpc('account/login/start',{'type':'apiKey','apiKey':os.environ['OPENAI_API_KEY']})
 async def send(self,v):self.proc.stdin.write((json.dumps(v,ensure_ascii=False)+'\n').encode());await self.proc.stdin.drain()
 async def rpc(self,method,params):
  self.seq+=1;i=self.seq;f=asyncio.get_running_loop().create_future();self.waiters[i]=f
  await self.send({'id':i,'method':method,'params':params});return await asyncio.wait_for(f,90)
 async def read(self):
  try:
   while line:=await self.proc.stdout.readline():
    m=json.loads(line)
    if 'method'in m and 'id'in m:
     if m['method']=='item/tool/call':
      p=m['params'];name=p['tool'];args=p.get('arguments',{})
      try:
       value=await asyncio.to_thread(self.tool,name,args);self.calls.append({'name':name,'status':'complete'})
       result={'success':True,'contentItems':[{'type':'inputText','text':json.dumps(value,ensure_ascii=False,default=str)}]}
      except Exception as e:
       self.calls.append({'name':name,'status':'failed','error_type':type(e).__name__});result={'success':False,'contentItems':[{'type':'inputText','text':json.dumps({'available':False,'error_type':type(e).__name__,'note':str(e)[:350],'unknown_is_not_zero':True},ensure_ascii=False)}]}
      await self.send({'id':m['id'],'result':result})
     elif m['method'].endswith('requestApproval'):await self.send({'id':m['id'],'result':{'decision':'decline'}})
     else:await self.send({'id':m['id'],'error':{'code':-32601,'message':'Only scoped analytical tools are available'}})
    elif 'id'in m:
     f=self.waiters.pop(m['id'],None)
     if f and not f.done():
      if 'error'in m:f.set_exception(RuntimeError('Codex RPC '+str(m['error'].get('code'))+': '+str(m['error'].get('message'))[:300]))
      else:f.set_result(m.get('result',{}))
    elif m.get('method')=='item/completed':
     item=m.get('params',{}).get('item',{})
     if item.get('type')=='agentMessage'and item.get('phase')=='final_answer':self.final.append(item['text'])
    elif m.get('method')=='turn/completed':
     turn=m['params']['turn']
     if self.finished and not self.finished.done():
      if turn['status']=='completed':self.finished.set_result(turn)
      else:self.finished.set_exception(RuntimeError('Codex turn '+turn['status']))
  except Exception as e:
   if self.finished and not self.finished.done():self.finished.set_exception(e)
  finally:
   for f in self.waiters.values():
    if not f.done():f.set_exception(RuntimeError('Codex transport closed'))
 async def turn(self,state,prompt,instructions,specs):
  params={'model':self.model,'cwd':str(self.home),'approvalPolicy':'never','sandbox':'read-only','developerInstructions':instructions}
  if state:
   path=self.home/'restored-session.jsonl';raw=restore_rollout(state,specs)
   path.write_bytes(raw)
   result=await self.rpc('thread/resume',dict(params,threadId=state['thread_id'],path=str(path),excludeTurns=True))
  else:result=await self.rpc('thread/start',dict(params,dynamicTools=specs,historyMode='legacy',serviceName='veschi_telegram'))
  self.thread=result['thread'];self.finished=asyncio.get_running_loop().create_future()
  await self.rpc('turn/start',{'threadId':self.thread['id'],'input':[{'type':'text','text':prompt}],'effort':'medium'})
  await asyncio.wait_for(self.finished,420)
  if not self.final:raise RuntimeError('Codex completed without final answer')
  return '\n'.join(self.final)
 async def snapshot(self):
  info=await self.rpc('thread/read',{'threadId':self.thread['id'],'includeTurns':False})
  path=info['thread'].get('path')or self.thread.get('path')
  if not path or not Path(path).is_file():raise RuntimeError('Native Codex rollout missing; cannot claim persistent dialogue')
  raw=Path(path).read_bytes()
  if len(raw)>8000000:raise RuntimeError('Native thread needs compaction before persistence')
  return dict(thread_id=self.thread['id'],model=self.model,rollout_gzip_b64=encode(raw),rollout_sha256=hashlib.sha256(raw).hexdigest(),saved_at=stamp(),tools=self.calls)
 async def close(self):
  if getattr(self,'proc',None):
   self.proc.stdin.close()
   try:await asyncio.wait_for(self.proc.wait(),10)
   except asyncio.TimeoutError:self.proc.terminate();await self.proc.wait()
  if getattr(self,'log',None):self.log.close()