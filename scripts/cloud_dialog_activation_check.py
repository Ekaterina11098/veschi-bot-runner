"""Read-only runtime checks. No generation, messages, WB or old-job dispatch."""
import os,json
from urllib.request import Request,urlopen
from ooo_sol_dialog import DB,Worker,ROOT,CHAT,BOT
from bounded_sol_dialog import MODEL,stamp,dump
from china_no_paid import require_paid_api

def run():
 db=DB();china=db.get('china_agent:codex_cloud:v1:policy')or{}
 require_paid_api(china)
 if china.get('transport')!='responses_bounded_v1'or not china.get('dialogue_not_before'):raise RuntimeError('China bounded dialogue cutover missing')
 nopaid=db.get('china_agent:no_paid_ai:v1')or{}
 if nopaid.get('enabled')is not False:raise RuntimeError('Deterministic-only China routing still enabled')
 ip=db.get('advertising:ip:cloud:v1:policy')or{};rollout=db.get('advertising:dialog_rollout:v1')or{}
 if not(ip.get('enabled')is True and ip.get('model')==MODEL and ip.get('wb_permission')is False and rollout.get('enabled')is True and rollout.get('chat_id')==ip.get('chat_id')):raise RuntimeError('IP dialogue policy not ready')
 ooo=db.get(ROOT+'policy')or{}
 if not(ooo.get('enabled')is True and ooo.get('model')==MODEL and ooo.get('chat_id')==CHAT and ooo.get('bot_id')==BOT and ooo.get('wb_permission')is False):raise RuntimeError('OOO dialogue policy not ready')
 worker=Worker(db);verified=worker.preflight()
 req=Request('https://api.openai.com/v1/models/'+MODEL,headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']})
 with urlopen(req,timeout=30)as r:model=json.load(r)
 if model.get('id')!=MODEL:raise RuntimeError('Sol API model access not confirmed')
 result={'status':'ready_for_new_questions','model':MODEL,'china':True,'ip':True,'ooo':True,'ooo_destination_verified':verified['status']=='verified','paid_generation_calls':0,'wb_writes':0,'telegram_sends':0,'old_jobs_replayed':0,'observed_at':stamp(),'run_id':os.environ.get('GITHUB_RUN_ID')}
 db.put(ROOT+'activation_check',result);return result
if __name__=='__main__':print(dump(run()))
