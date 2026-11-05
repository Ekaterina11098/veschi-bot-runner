import os,sys,json
import fbs_document_chain as m

class ScopedCache(m.Cache):
 def __init__(self,t,cabinet):super().__init__(t);self.cabinet=cabinet
 def scope(self,key):return key.replace("fbs_document_chain:china:","fbs_document_chain:"+self.cabinet+":",1)
 def get(self,key):return super().get(self.scope(key))
 def put(self,key,value):return super().put(self.scope(key),value)

def main(mode):
 tokens={k:os.environ["WB_TOKEN_"+v] for k,v in {"china":"3","ip":"2","ooo":"1"}.items()}
 results={}
 for cabinet in (["ip","ooo"] if mode=="setup" else ["china","ip","ooo"]):
  os.environ["WB_TOKEN_3"]=tokens[cabinet]
  m.CONFIG="fbs_document_chain:"+cabinet+":config:v1"
  m.STATE="fbs_document_chain:"+cabinet+":state:v1"
  m.PREFIX="fbs_document_chain:"+cabinet+":supply:v1:"
  t=m.Transport();db=ScopedCache(t,cabinet);c=db.get(m.CONFIG)
  if not c:raise m.Stop("Cabinet configuration missing: "+cabinet)
  w=m.Worker(t,db,c)
  try:
   if mode=="setup":
    if c.get("writes_enabled"):raise m.Stop("Already enabled; setup cannot reset baseline")
    results[cabinet]=w.run("preview")
    if not db.get(m.STATE):w.run("bootstrap")
    c["setup_verified_at"]=m.now();c["status"]="preview_verified"
    db.put(m.CONFIG,c)
   else:
    results[cabinet]=w.run(mode)
    if mode=="run" and os.environ.get("FBS_EXECUTION_KIND")=="daily" and results[cabinet].get("status")=="waiting_for_daily_time":
     detail={**results[cabinet],"status":"missed_daily_schedule","owner_confirmation_required":True,"message":"Плановый запуск пришел вне разрешенного времени. Списания не выполнены; требуется согласование внепланового запуска."}
     db.put("fbs_document_chain:"+cabinet+":missed_daily_run:v1",detail)
     results[cabinet]=detail
  except Exception as e:
   db.put("fbs_document_chain:"+cabinet+":worker_error:v1",{"at":m.now(),"error":str(e) if isinstance(e,m.Stop) else type(e).__name__})
   results[cabinet]={"status":"failed"}
 print(json.dumps(results))
 if any(x.get("status") in ("failed","missed_daily_schedule") for x in results.values()):sys.exit(1)
if __name__=="__main__":main(sys.argv[1] if len(sys.argv)>1 else "run")
