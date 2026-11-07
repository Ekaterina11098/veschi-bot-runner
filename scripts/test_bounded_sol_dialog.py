import unittest
from bounded_sol_dialog import BoundedSol,compact_message,MODEL
class DB:
 def __init__(self):self.v={}
 def get(self,k):return self.v.get(k)
 def once(self,k,v):
  if k in self.v:raise RuntimeError('Duplicate claim')
  self.v[k]=v.copy()
 def update(self,k,v):self.v[k]=v.copy()
class Tests(unittest.TestCase):
 def test_no_repeat_and_no_hidden_history_or_tools(self):
  calls=[]
  def api(path,body):
   calls.append((path,body))
   return {'input_tokens':100}if path.endswith('input_tokens')else{'status':'completed','model':MODEL,'id':'r1','usage':{'input_tokens':100,'output_tokens':10},'output':[{'type':'message','content':[{'type':'output_text','text':'Ответ'}]}]}
  w=BoundedSol(DB(),'test:',api)
  self.assertEqual(w.answer('a','rules','question'),'Ответ');self.assertEqual(w.answer('a','rules','question'),'Ответ')
  self.assertEqual(len(calls),2);self.assertEqual(calls[1][1]['tools'],[]);self.assertNotIn('previous_response_id',calls[1][1])
 def test_uncertain_submission_is_not_repeated(self):
  calls=[]
  def api(path,body):
   calls.append(path)
   if path.endswith('input_tokens'):return {'input_tokens':100}
   raise TimeoutError()
  w=BoundedSol(DB(),'test:',api)
  with self.assertRaises(TimeoutError):w.answer('a','rules','question')
  with self.assertRaises(RuntimeError):w.answer('a','rules','question')
  self.assertEqual(len(calls),2)
 def test_oversize_count_does_not_submit(self):
  calls=[]
  w=BoundedSol(DB(),'test:',lambda p,b:calls.append(p)or{'input_tokens':12001})
  with self.assertRaises(ValueError):w.answer('a','rules','question')
  self.assertEqual(calls,['responses/input_tokens'])
 def test_compaction_preserves_question_and_explains_coverage(self):
  import json
  v=json.loads(compact_message({'runtime_scope':{'chat_id':1},'untrusted_telegram_question':'question','dated_work_context':{'analytics':'x'*50000,'work_notes':'x'*50000}}))
  self.assertEqual(v['untrusted_telegram_question'],'question');self.assertLess(len(str(v)),20000);self.assertIn('excerpt',v['dated_work_context']['analytics'])
if __name__=='__main__':unittest.main()
