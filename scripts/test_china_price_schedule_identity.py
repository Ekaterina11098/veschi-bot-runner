"""Offline checks: manual reports cannot suppress scheduled identities or spend chat tokens."""
import argparse,ast,sys,types,unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
def function(path,name,namespace):
 tree=ast.parse(Path(__file__).with_name(path).read_text(encoding='utf8'))
 node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name==name)
 exec(compile(ast.Module(body=[node],type_ignores=[]),path,'exec'),namespace)
 return namespace[name]
class Contract(unittest.TestCase):
 def identities(self,args):
  result=[]
  class Worker:
   def __init__(self,section):
    self.day=date(2026,11,12);self.section=section;self.command='report_'+section;self.update_id=-(9800000000 if section=='candidates' else 9900000000)-2507;self.audit={};self.original_http=lambda:None
   def run(self,preview=False):
    result.append((self.update_id,getattr(self,'delivery_mode',None)));self.audit['status']='delivered'
   def save(self,*args):pass
  main=function('china_morning_pair.py','main',dict(argparse=argparse,PairWorker=Worker,date=date,json=__import__('json')))
  with patch.object(sys,'argv',['test']+args),patch.dict(sys.modules,{'requests':types.SimpleNamespace(sessions=types.SimpleNamespace(Session=types.SimpleNamespace(request=None)))}):main()
  return result
 def test_manual_identities_do_not_consume_scheduled_jobs(self):
  normal=self.identities([]);manual=self.identities(['--send-now'])
  self.assertTrue(set(x[0]for x in normal).isdisjoint(x[0]for x in manual))
  self.assertEqual([x[1]for x in manual],['morning-manual','control-manual'])
 def test_correction_has_own_durable_identity(self):
  self.assertEqual(self.identities(['--send-now','--correct-candidates','--section','candidates']),[(-9700002507,'morning-corrected')])
 def test_paid_chat_permission_does_not_enable_price_model(self):
  def forbidden():raise AssertionError('Paid model must not be constructed')
  review=function('china_codex_reports.py','review_price',dict(Core=forbidden))
  w=types.SimpleNamespace(mode='morning',day=date(2026,11,12),price_control_review={'status':'complete_disclosed_forecast_model'},get=lambda key:{'paid_api_allowed':True})
  with patch.dict(sys.modules,{'china_price_current_check':types.SimpleNamespace(check=lambda w,a:a)}):
   answer,trace=review(w,'checked',[{'name':'china_price_daily_report','status':'complete_orders'}])
  self.assertEqual(answer,'checked');self.assertEqual(trace[-1]['model_calls'],0)
if __name__=='__main__':unittest.main()
