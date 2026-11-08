import copy,unittest
from datetime import datetime,timezone
from unittest.mock import patch
import china_free_ads as f
import china_no_paid as n
from china_new_ads import REQUEST

class W:
 def __init__(self):
  self.now=datetime.now(timezone.utc);self.values={};self.queries=[]
 def get(self,k):return self.values.get(k)
 def save(self,k,v,insert=False):
  if insert and k in self.values:return False
  self.values[k]=copy.deepcopy(v);return True
 def catalog(self):return [('100','59-Noel-grey'),('200','63-Noel-blue'),('300','99-other')]
 def db(self,*a,**kw):
  self.queries.append(kw)
  return [{'payload':{'answer':'| Кандидат | Прибыль |\n|---|---|\n| 59 — Noel серая | +10 |\n| 63 — Noel синяя | +20 |'}}]
def job(text='Добавь на них рекламу'):
 return dict(id=263,chat_id=-1004342917488,sender_id=307200273,request_text=text,tool_trace=[dict(name='china_saved_question',bot_id=8780468043,message_id=754,reply_message_id=737,codex_bridge=True,bridge_request_text=text)])

class FreeAds(unittest.TestCase):
 def test_paid_api_requires_enabled_current_scoped_policy(self):
  p=dict(enabled=True,paid_api_allowed=True,chat_id=-1004342917488,bot_id=8780468043,model='gpt-6.1-sol',wb_action_permission=False)
  self.assertTrue(n.require_paid_api(p))
  for invalid in [None,{},dict(p,enabled=False),dict(p,paid_api_allowed=False),dict(p,chat_id=1),dict(p,bot_id=1),dict(p,model='other')]:
   with self.assertRaises(PermissionError):n.require_paid_api(invalid)
 def test_reference_resolves_delivered_target_list_only(self):
  w=W();self.assertEqual(f.requested_ids(w,job(),'Добавь на них рекламу'),[100,200])
  q=w.queries[0]['params'];self.assertEqual(q['payload->>status'],'eq.delivered');self.assertEqual(q['payload->message_ids'],'cs.[737]')
 def test_unresolved_reference_does_not_create_request(self):
  w=W();w.db=lambda *a,**k:[]
  result=f.handle(w,job())
  self.assertIn('Не найден',result);self.assertEqual(w.values,{})
 def test_unknown_explicit_article_never_becomes_cabinet_wide(self):
  with self.assertRaises(ValueError):f.requested_ids(W(),job(),'Добавь 999-unknown в рекламу')
  with self.assertRaises(ValueError):f.requested_ids(W(),job(),'Добавь 59 в рекламу')
 def test_launch_request_asks_consent_before_preparing(self):
  w=W()
  with patch('china_group_permissions.allowed',return_value=True):
   result=f.handle(w,job('Ты запустил на них рекламу? Если еще нет то запусти'))
  from china_ad_proposal_consent import QUESTION
  req=w.get(QUESTION+'263')
  self.assertEqual(req['nm_ids'],[100,200]);self.assertFalse(req['grants_action_permission'])
  self.assertIn('Подготовить',result);self.assertIsNone(w.get(REQUEST+'263'))
  self.assertFalse(any('approval' in k for k in w.values))
 def test_negative_and_status_question_do_not_prepare(self):
  for text in ['Не запускай рекламу','Ты запустил рекламу?']:
   w=W();f.handle(w,job(text));self.assertEqual(w.values,{})
 def test_bridged_confirmation_requires_exact_original_text(self):
  j=job('согласен');j['request_text']='/codex согласен'
  self.assertEqual(f.confirmation_text(j),'согласен')
  j['tool_trace'][0]['bridge_request_text']='делай'
  self.assertEqual(f.confirmation_text(j),'/codex согласен')
 def test_candidate_scope_is_applied_before_selection(self):
  from china_new_ad_reports import choose
  source=dict(memory_used=True,campaigns={},protected=[],experience={},prices=[],stock=[],orders=[],policy={'logistics_by_nm':{}},products=[{'nm_id':999}])
  groups,_=choose(source,nm_ids=[100]);self.assertEqual(groups,{'orders':[],'demand':[]})
 def test_continuation_processes_one_job_only(self):
  from china_free_ad_work import run
  w=W();w.db=lambda *a:[{'id':263,'status':'done'}]
  with patch('china_new_ad_reports.process_requests') as process:
   result=run(w,263)
  process.assert_called_once_with(w,job_id=263);self.assertEqual(result['paid_model_calls'],0)
if __name__=='__main__':unittest.main()


