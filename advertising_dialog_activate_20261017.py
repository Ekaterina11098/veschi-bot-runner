"""Activate only the verified dialogue source pin; no question execution or sending."""
import os,sys,json,copy,hashlib
sys.path.insert(0,'private-source')
from advertising_agent import agent_store as store
from stock_deploy_support import seal
KEY='advertising:dialog_rollout:v1'
proof=dict(complete=False,source_calls=0,model_calls=0,telegram_sends=0,wb_writes=0)
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
try:
 r=store.registration()
 rows=store.db('GET','telegram_api_cache',params={'cache_key':'eq.'+KEY,'select':'payload,updated_at','limit':1}) or []
 if len(rows)!=1:raise RuntimeError('Existing rollout missing')
 old=rows[0]['payload'];target=os.environ['ADVERTISING_DIALOG_SOURCE_SHA']
 if old.get('enabled') is not True or old.get('chat_id')!=r['chat_id'] or old.get('owner_id')!=r['registered_by_user_id']:raise RuntimeError('Existing rollout identity mismatch')
 if old.get('source_sha') not in ('c06863252b707f82fea155919940075596c8aa33',target):raise RuntimeError('Unexpected existing source pin')
 before=store.cache_get('advertising:ip_pair_decisions:token_2:v1')
 new=dict(old,source_sha=target)
 if new!=old:
  patched=store.db('PATCH','telegram_api_cache',params={'cache_key':'eq.'+KEY,'updated_at':'eq.'+rows[0]['updated_at'],'select':'payload'},body={'payload':new,'updated_at':store.now().isoformat()},prefer='return=representation') or []
  if len(patched)!=1:raise RuntimeError('Rollout CAS failed')
 if store.cache_get(KEY)!=new:raise RuntimeError('Rollout readback mismatch')
 if digest(before)!=digest(store.cache_get('advertising:ip_pair_decisions:token_2:v1')):raise RuntimeError('Recommendation registry changed')
 proof.update(complete=True,source_sha=target,rollout_readback_verified=True,registry_unchanged=True)
except Exception as exc:proof.update(error_type=type(exc).__name__,error=str(exc)[:160])
seal('advertising-dialog-activation',proof)
print(json.dumps(proof))
if not proof['complete']:raise SystemExit(1)
