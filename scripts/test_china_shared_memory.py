import copy,unittest
from datetime import datetime,timezone
from china_shared_memory import POLICY,ROOT,context,remember,record_turn,is_work

class W:
 now=datetime(2026,10,25,19,tzinfo=timezone.utc)
 def __init__(self):
  self.rows={POLICY:dict(enabled=True,work_chat_ids=[-77],owner_user_id=5)}
  self.queries=[]
 def get(self,k):return copy.deepcopy(self.rows.get(k))
 def save(self,k,v,insert=False):
  if not insert or k not in self.rows:self.rows[k]=copy.deepcopy(v)
  return True
 def db(self,method,table,params):
  self.queries.append(params)
  prefix=params['cache_key'][5:-1]
  return [dict(cache_key=k,payload=v) for k,v in reversed(list(self.rows.items())) if k.startswith(prefix)][:params['limit']]

def job(text='Проверь рекламную кампанию',**kw):
 return dict(id=8,chat_id=-77,sender_id=5,request_text=text,**kw)

class SharedMemory(unittest.TestCase):
 def test_disabled_or_other_channel_cannot_read(self):
  w=W();self.assertFalse(context(w,dict(chat_id=-78))['available']);self.assertFalse(w.queries)
 def test_only_work_prefix_queried_even_with_private_rows(self):
  w=W();w.rows['china_agent:shared_memory:v1:private:5:note:secret']=dict(quote='private')
  c=context(w,job())
  self.assertNotIn('private',str(c['notes']))
  self.assertTrue(all(q['cache_key'].startswith('like.'+ROOT) for q in w.queries))
 def test_owner_can_save_exact_current_quote(self):
  w=W();j=job('Запомни: отчёт по РК разбивай на PNG')
  r=remember(w,j,'report-format','отчёт по РК разбивай на PNG')
  self.assertTrue(r['saved']);self.assertFalse(w.get(r['source_key'])['grants_action_permission'])
 def test_non_owner_cannot_replace_agreements(self):
  w=W();j=job('Запомни: отчёт по РК разбивай на PNG');j['sender_id']=6
  with self.assertRaises(PermissionError):remember(w,j,'report','отчёт по РК разбивай на PNG')
 def test_no_invented_quote_or_implicit_memory_write(self):
  w=W()
  with self.assertRaises(ValueError):remember(w,job(),'report','отчёт по РК разбивай на PNG')
 def test_private_and_secret_notes_never_exported(self):
  for text in ['Запомни личное: отчёт врача','Запомни: секрет для рекламы','Запомни: мой пароль для WB']:
   with self.assertRaises(ValueError):remember(W(),job(text),'secret',text)
 def test_latest_owner_correction_wins_without_erasing_history(self):
  w=W()
  remember(w,job('Запомни: отчёт короткий'),'format','отчёт короткий')
  j=job('Запомни: отчёт подробный');j['id']=9
  remember(w,j,'format','отчёт подробный')
  c=context(w,j)
  self.assertEqual([r['quote'] for r in c['notes']],['отчёт подробный'])
  self.assertEqual(len([k for k in w.rows if k.startswith(ROOT+'note:')]),2)
 def test_forget_is_tombstone_and_keeps_audit(self):
  w=W();remember(w,job('Запомни: отчёт короткий'),'format','отчёт короткий')
  j=job('Забудь: отчёт короткий');j['id']=9
  remember(w,j,'format','отчёт короткий',True)
  self.assertEqual(context(w,j)['notes'],[])
 def test_turns_are_idempotent_and_not_receipts(self):
  w=W();j=job()
  self.assertTrue(record_turn(w,j,'Предлагаю исключить товар'))
  self.assertTrue(record_turn(w,j,'другой ответ'))
  rows=context(w,j,query='реклам')['conversation']
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['answer'],'Предлагаю исключить товар')
  self.assertFalse(rows[0]['assistant_answer_is_verified_fact'])
 def test_personal_turns_and_simulation_not_recorded(self):
  w=W()
  self.assertFalse(record_turn(w,job('Обсудим здоровье и рекламу'),'ok'))
  self.assertFalse(record_turn(w,job('Как испечь пирог?'),'ok'))
  j=job();j['id']=-1;self.assertFalse(record_turn(w,j,'ok'))
 def test_general_chat_does_not_require_wb(self):
  self.assertFalse(is_work('Напиши поздравление маме'))
  self.assertTrue(is_work('Какие РК добавили сегодня?'))
 def test_codex_handoff_visible_to_telegram(self):
  w=W();w.rows[ROOT+'note:codex']=dict(kind='codex_handoff',visibility='work',topic='pending',status='active',quote='План обсуждён в Codex, не исполнен')
  self.assertIn('не исполнен',context(w,job())['notes'][0]['quote'])

class DialogIntegration(unittest.TestCase):
 def test_general_question_answers_without_marketplace_tools(self):
  import sys
  import test_china_analytic_dialog as base
  import china_analytic_dialog as dialog
  from unittest.mock import patch
  w=base.W();bodies=[]
  def model(body):
   bodies.append(body)
   return dict(output=[dict(type='message',content=[dict(type='output_text',text='С днём рождения! Желаю радости и здоровья.')])])
  w.model_request=model
  with patch.dict(sys.modules,base.Rules().modules()),patch('china_experience.decision_context',side_effect=AssertionError('Unneeded business scan')):
   answer,_=dialog.answer(w,dict(id=99,chat_id=-77,request_text='Напиши короткое поздравление маме',tool_trace=[]),[])
  self.assertIn('рождения',answer);self.assertEqual(bodies[0]['tool_choice'],'auto')
  self.assertFalse(any(t['name'] in ['get_live_data','get_wb_evidence'] for t in bodies[0]['tools']))
 def test_codex_work_note_enters_telegram_model_context(self):
  import sys,json
  import test_china_analytic_dialog as base
  import china_analytic_dialog as dialog
  from unittest.mock import patch
  w=base.W();w.mem[POLICY]=dict(enabled=True,work_chat_ids=[-77],owner_user_id=5)
  note=dict(kind='codex_handoff',visibility='work',topic='pending',status='active',quote='Решение из Codex: новый план ещё не выполнен.')
  w.db=lambda method,table,params:([dict(payload=note)] if params.get('cache_key','').startswith('like.'+ROOT+'note:') else [])
  bodies=[]
  def model(body):
   bodies.append(body)
   return dict(output=[dict(type='message',content=[dict(type='output_text',text='Новый план обсуждён, но ещё не выполнен.')])])
  w.model_request=model
  with patch.dict(sys.modules,base.Rules().modules()),patch('china_experience.decision_context',return_value=dict(experiences=[],recent_changed_nm_ids=[])):
   answer,_=dialog.answer(w,dict(id=99,chat_id=-77,request_text='Что решили по рекламе?',tool_trace=[]),[])
  self.assertIn('Решение из Codex',json.dumps(bodies[0]['input'],ensure_ascii=False));self.assertIn('не выполнен',answer)

if __name__=='__main__':unittest.main()
