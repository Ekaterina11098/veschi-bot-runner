import json,unittest
from pathlib import Path
from china_article_diagnostic import evaluate,requested,render
from test_china_article_diagnostic import fact,NOW
CORPUS=json.loads(Path(__file__).with_name('china_article_pavel_cases.json').read_text(encoding='utf-8'))
class PavelReplays(unittest.TestCase):pass
def case_test(case):
 def test(self):
  f=fact();kind=case['variant'];stage=case['expected_stage']
  self.assertEqual(requested(case['request']),stage is not None)
  if stage is None:return
  if kind=='restock':f['availability_events']=[dict(source='human_statement',at=NOW.isoformat())]
  if kind in ['recent','price']:f['changes']=[dict(kind='price' if kind=='price' else 'bid',verified=True,at=NOW.isoformat(),cid=40000002)]
  if kind=='views':
   for d in f['daily']:d['views']=100
  if kind in ['clicks','baskets']:
   for d in f['daily']:d.update(views=100,clicks=10,baskets=1 if kind=='baskets' else 0)
  if kind=='reserve':f['stock']['available']=0
  if kind=='budget':f['campaign']['budget_cny']=0
  if kind=='rating':f['quality']['rating']=3.2
  if kind=='unrated':f['quality'].update(rating=None,review_count=0)
  if kind=='unknown_rating':f['quality'].update(rating=None,review_count=None)
  if kind=='missing':f['daily']=[]
  if kind=='shipping':f['economy']['logistics_cny']=None
  if kind=='today':f['today_observation']=dict(counters=dict(spend=500,orders=0,amount=0))
  result=evaluate(f,NOW)
  self.assertEqual(result['stage'],stage)
  answer=render(dict(rows=[result],period_from='2026-10-25',period_to='2026-10-27'))
  self.assertEqual(result['wb_writes'],0);self.assertFalse(result['execution_authorized'])
  for bad in ['проверьте','получите тариф','сравните с конкурентами','гарантирован','ДРР 0%']:self.assertNotIn(bad,answer)
  if stage!='limited_traffic_test':self.assertEqual(result['recommendation'],'Нет')
 return test
for case in CORPUS['cases']:setattr(PavelReplays,'test_'+case['id'],case_test(case))
if __name__=='__main__':unittest.main()
