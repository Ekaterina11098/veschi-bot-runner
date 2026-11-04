import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import Mock
from review_morning import collection_plan,resume_collection
from review_china_two_hour import run
class ChinaTwoHourTests(unittest.TestCase):
 def plan(self,hour,minute=0,day=4):
  return collection_plan('feedbacks',True,datetime(2026,11,day,hour,minute,tzinfo=timezone.utc))
 def test_only_china_around_clock_with_moscow_bucket_and_day(self):
  for hour in range(24):
   p=self.plan(hour)
   self.assertEqual(p['cabinets'],('token_3',))
   self.assertEqual(int(p['cycle_slot'][-2:])%2,0)
  self.assertEqual(self.plan(21)['day'],'2026-11-05')
  self.assertEqual(self.plan(21)['cycle_slot'],'2026-11-05:00')
 def test_same_bucket_does_not_repeat_collection(self):
  p=self.plan(9,17);state=dict(status='complete',cycle_slot=p['cycle_slot'],items={'token_3:old':{'status':'confirmed'}},scopes={'token_3':{'status':'complete'}})
  self.assertFalse(resume_collection(state,p))
  p2=self.plan(11,17)
  self.assertTrue(resume_collection(state,p2))
  self.assertEqual(state['cycle_slot'],p2['cycle_slot'])
  self.assertEqual(state['items'],{'token_3:old':{'status':'confirmed'}})
  self.assertEqual(state['scopes'],{})
 def test_partial_collection_keeps_original_checkpoint_across_slot_boundary(self):
  old=self.plan(9);new=self.plan(11)
  state=dict(status='collecting',cycle_slot=old['cycle_slot'],scopes={'token_3':{'skip':100,'items':[{'id':'x'}]}})
  self.assertTrue(resume_collection(state,new))
  self.assertEqual(state['cycle_slot'],old['cycle_slot'])
  self.assertEqual(state['scopes']['token_3']['skip'],100)
 def test_other_cabinets_and_questions_keep_morning_window(self):
  now=datetime(2026,11,4,5,tzinfo=timezone.utc)
  p=collection_plan('feedbacks',False,now)
  self.assertEqual(p['cabinets'],('token_1','token_2'))
  self.assertEqual(p['control'],'reviews-morning:2026-11-04')
  state={'status':'collecting','scopes':{},'items':{}}
  self.assertTrue(resume_collection(state,p))
  self.assertTrue(state['scopes']['token_3']['delegated'])
  self.assertEqual(state['scopes']['token_3']['status'],'complete')
  self.assertEqual(collection_plan('questions',False,now)['cabinets'],('token_1','token_2','token_3'))
  self.assertIsNone(collection_plan('feedbacks',False,datetime(2026,11,4,12,tzinfo=timezone.utc)))
  with self.assertRaises(ValueError):collection_plan('questions',True,now)
 def test_busy_or_partial_retries_same_native_collector_then_stops_complete(self):
  collect=Mock(side_effect=[{'status':'busy'},{'status':'collecting'},{'status':'complete'}])
  sleep=Mock()
  self.assertEqual(run(collect,sleep=sleep,clock=lambda:0)['status'],'complete')
  self.assertEqual(sleep.call_count,2)
  for c in collect.call_args_list:self.assertEqual(c.kwargs,dict(kind='feedbacks',china_two_hour=True))
 def test_workflow_has_only_china_credentials_and_no_publisher_entry_point(self):
  text=(Path(__file__).parent/'.github/workflows/reviews-china-two-hour.yml').read_text(encoding='utf-8')
  self.assertIn("17 1-23/2 * * *",text)
  self.assertIn('WB_TOKEN_3:',text)
  self.assertNotIn('WB_TOKEN_1:',text);self.assertNotIn('WB_TOKEN_2:',text)
  self.assertIn('REVIEW_SEMANTIC_AUTO_FIVE_STAR:',text)
  self.assertNotIn('review_approved_worker.py',text)

 def test_real_main_uses_china_event_key_instead_of_morning_event(self):
  import ast,inspect,textwrap
  from review_morning import main
  tree=ast.parse(textwrap.dedent(inspect.getsource(main)))
  assignment=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='control' for t in n.targets))
  for china in (True,False):
   plan=collection_plan('feedbacks',china,datetime(2026,11,4,5,tzinfo=timezone.utc))
   key=eval(compile(ast.Expression(assignment.value),'<event-key>','eval'),dict(plan=plan,kind='feedbacks',day=plan['day']))
   self.assertEqual(key,plan['control'])
  self.assertNotEqual(collection_plan('feedbacks',True,datetime(2026,11,4,5,tzinfo=timezone.utc))['control'],'reviews-morning:2026-11-04')



