import os,json,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from unittest.mock import Mock,patch
import review_semantic_positive as semantic
from review_auto_five_star import classify
class SemanticPositiveTests(unittest.TestCase):
 def setUp(self):
  semantic.assess.cache_clear()
  self.env=patch.dict(os.environ,{'REVIEW_SEMANTIC_AUTO_FIVE_STAR':'1','OPENAI_API_KEY':'test-only'});self.env.start()
  self.result=dict(label='POSITIVE',has_complaint=False,has_question=False,has_uncertainty=False,confidence=0.99)
 def tearDown(self):self.env.stop();semantic.assess.cache_clear()
 def response(self,result=None):
  return {'choices':[{'message':{'content':json.dumps(self.result if result is None else result)}}]}
 def test_novel_positive_all_fields_are_passed_as_untrusted_data(self):
  with patch('review_semantic_positive.request_assessment',return_value=self.response()) as post:
   self.assertTrue(classify(dict(productValuation=5,text='Моя любимая сумочка. Подходит под разные образы',pros='Очень идет к пальто',cons='Все замечательно'))['eligible'])
   sent=post.call_args.args[0];data=json.loads(sent['messages'][1]['content'])
   self.assertEqual(set(data),{'text','pros','cons'})
   self.assertIn('untrusted',sent['messages'][0]['content'])
   self.assertEqual(sent['response_format']['type'],'json_schema')
 def test_concern_question_uncertainty_or_lower_confidence_remain_manual(self):
  for change in [dict(label='COMPLAINT'),dict(has_complaint=True),dict(has_question=True),dict(has_uncertainty=True),dict(confidence=0.97),dict(label='UNCERTAIN')]:
   semantic.assess.cache_clear()
   with patch('review_semantic_positive.request_assessment',return_value=self.response(dict(self.result,**change))):
    self.assertFalse(semantic.classify_fields('Незнакомая фраза','','')['eligible'])
 def test_api_failure_and_malformed_output_fail_closed(self):
  with patch('review_semantic_positive.request_assessment',side_effect=TimeoutError()):
   self.assertFalse(semantic.classify_fields('Новый текст','','')['eligible'])
  for value in [{},dict(self.result,has_complaint='false'),dict(self.result,confidence=True)]:
   semantic.assess.cache_clear()
   with patch('review_semantic_positive.request_assessment',return_value=self.response(value)):
    self.assertFalse(semantic.classify_fields('Новый текст','','')['eligible'])
 def test_exact_source_cache_never_reuses_decision_for_changed_cons(self):
  with patch('review_semantic_positive.request_assessment',return_value=self.response()) as post:
   semantic.classify_fields('Фраза','','')
   semantic.classify_fields('Фраза','','')
   semantic.classify_fields('Фраза','','Порвалась')
   self.assertEqual(post.call_count,2)
 def test_disabled_or_missing_key_never_calls_api(self):
  with patch.dict(os.environ,{'REVIEW_SEMANTIC_AUTO_FIVE_STAR':'0'}),patch('review_semantic_positive.request_assessment') as post:
   self.assertFalse(semantic.classify_fields('Текст','','')['eligible']);post.assert_not_called()
 def test_already_answered_and_nonfive_never_call_semantic(self):
  with patch('review_semantic_positive.request_assessment') as post:
   self.assertFalse(classify(dict(productValuation=4,text='Новая похвала'))['eligible'])
   self.assertFalse(classify(dict(productValuation=5,text='Новая похвала',answer={'text':'Ответ'}))['eligible'])
   post.assert_not_called()
