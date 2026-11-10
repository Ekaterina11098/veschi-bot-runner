import copy,importlib.util,sys,types,unittest
from pathlib import Path
from unittest.mock import Mock,patch
spec=importlib.util.spec_from_file_location('owner_snapshot',Path(__file__).with_name('china_midday_owner_snapshot.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class DB:
 def __init__(self,values):self.values=copy.deepcopy(values)
 def get(self,key):return copy.deepcopy(self.values.get(key))
 def create(self,key,value):
  if key in self.values:return False
  self.values[key]=copy.deepcopy(value);return True
 def put(self,key,value):self.values[key]=copy.deepcopy(value)
class OwnerSnapshot(unittest.TestCase):
 def data(self):
  bundle=dict(day='2026-11-10',campaigns=[dict(id=1,attention=[dict(action=dict(id='a',kind='ad_set_bid',target_minor=21))])])
  approval=dict(status='approved',owner_id=5122667182,chat_id=-1004342917488,scope='publish_report_only',bundle=bundle,bundle_sha256=m.digest(bundle),actions_sha256=m.digest([bundle['campaigns'][0]['attention'][0]['action']]))
  return approval
 def test_exact_approved_snapshot_releases_only_pre_submission_owner_hold(self):
  approval=self.data();key='china_agent:advertising_midday_owner_approved:2026-11-10:v1';delivery='china_agent:advertising_midday_delivery:2026-11-10:v1'
  db=DB({key:approval,delivery:dict(status='blocked_by_owner_full_validation',parts=[dict(status='blocked_by_owner')])})
  deliver=Mock(return_value=dict(status='delivered',parts=[dict(kind='drr:001',status='sent',message_id=999)]))
  modules={'china_advertising_midday':types.SimpleNamespace(render_midday=lambda b:[dict(kind='drr:001',family='drr',page=1,total=1,bytes=b'png',actions=[dict(id='a')])]),'china_daily_ad_actions':types.SimpleNamespace(plan=lambda *a,**k:dict(plan_id='p',plan_sha256='hash',items=[1]),bind=Mock()),'china_advertising_delivery':types.SimpleNamespace(deliver=deliver,telegram_sender=lambda io:Mock())}
  with patch.dict(sys.modules,modules):m.publish(db,'2026-11-10')
  self.assertEqual('ready',db.get(delivery)['status']);deliver.assert_called_once()
 def test_changed_bundle_rejected_before_delivery(self):
  a=self.data();a['bundle']['campaigns'][0]['attention'][0]['action']['target_minor']=28
  with self.assertRaisesRegex(ValueError,'changed'):m.publish(DB({'china_agent:advertising_midday_owner_approved:2026-11-10:v1':a}),'2026-11-10')
 def test_publish_authorization_does_not_accept_wb_execution_scope(self):
  a=self.data();a['scope']='execute_wb'
  with self.assertRaisesRegex(ValueError,'scope'):m.publish(DB({'china_agent:advertising_midday_owner_approved:2026-11-10:v1':a}),'2026-11-10')
 def test_no_approval_has_no_side_effects(self):self.assertIsNone(m.publish(DB({}),'2026-11-10'))
if __name__=='__main__':unittest.main()