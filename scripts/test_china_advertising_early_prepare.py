import ast,json,os,sys,types,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import Mock,patch

class EarlyPrepare(unittest.TestCase):
 def execute(self,complete):
  source=Path(__file__).with_name('china_advertising_midday.py').read_text(encoding='utf-8')
  fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)and n.name=='run')
  calls=Mock();io=types.SimpleNamespace(get=lambda key:None)
  modules={
   'china_price_apply':types.SimpleNamespace(IO=lambda:io),
   'china_advertising_delivery':types.SimpleNamespace(deliver=calls.deliver,telegram_sender=calls.sender),
   'china_daily_ad_actions':types.SimpleNamespace(plan=calls.plan,bind=calls.bind),
   'china_midday_completed_review':types.SimpleNamespace(attach=Mock(return_value=dict(economic_review_complete=complete)),include_closed=lambda io,s,d:s)}
  class Clock:
   @staticmethod
   def now(tz):return datetime(2026,11,11,14,45,tzinfo=timezone(timedelta(hours=3)))
  scope=dict(os=os,datetime=Clock,MSK=timezone(timedelta(hours=3)),json=json,collect=lambda *a,**kw:{},prepare_midday=lambda *a:{})
  exec(compile(ast.Module(body=[fn],type_ignores=[]),'prepare','exec'),scope)
  with patch.dict(sys.modules,modules),patch.dict(os.environ,GITHUB_REPOSITORY='Ekaterina11098/veschi-bot-runner',GITHUB_REF='refs/heads/main'):
   scope['run']()
  calls.sender.assert_not_called();calls.deliver.assert_not_called();calls.plan.assert_not_called()
  return modules
 def test_complete_preparation_never_sends_early(self):
  modules=self.execute(True);modules['china_midday_completed_review'].attach.assert_called_once()
 def test_incomplete_preparation_fails(self):
  with self.assertRaisesRegex(ValueError,'full verification'):self.execute(False)

if __name__=='__main__':unittest.main()