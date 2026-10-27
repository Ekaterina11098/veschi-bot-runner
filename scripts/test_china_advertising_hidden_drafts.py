import copy,unittest
from unittest.mock import patch
from china_advertising_v2 import never_started_draft,build
from china_advertising_midday import prepare_midday
class IO:
 def get(self,key):return None
class HiddenDrafts(unittest.TestCase):
 def test_only_explicit_never_started_draft_hidden(self):
  self.assertTrue(never_started_draft(dict(status=4,timestamps=dict(started=None))))
  for c in [dict(status=9,timestamps=dict(started=None)),dict(status=11,timestamps=dict(started=None)),dict(status=4),dict(status=4,timestamps=dict(started='2026-10-01T00:00:00+03:00'))]:
   self.assertFalse(never_started_draft(c))
 def draft(self):return dict(id=40892162,status=4,timestamps=dict(started=None))
 def test_morning_draft_needs_no_budget_or_statistical_placeholder(self):
  source=dict(ids=[40892162],period_to='2026-10-26',observed_at='2026-10-27T04:00:00Z',catalogue=dict(rows=[]),executions=[],config={},batches={'0':dict(campaigns=dict(adverts=[self.draft()]),stats=[],budgets=dict(adverts=[]))})
  original=copy.deepcopy(source)
  self.assertEqual([],build(source)['campaigns'])
  self.assertEqual(original,source)
 def test_midday_hides_draft_and_keeps_active_and_paused(self):
  active=dict(id=1,status=9,timestamps=dict(started='2026-10-01T00:00:00+03:00'),settings=dict(name='Active',placements=dict(search=True)),nm_settings=[])
  paused=dict(active,id=2,status=11,settings=dict(name='Paused',placements=dict(search=True)))
  source=dict(observed_at='2026-10-27T12:00:00Z',catalogue=dict(rows=[]),executions=[],batches={'0':dict(campaigns=dict(adverts=[self.draft(),active,paused]),stats=[])})
  with patch('china_advertising_midday.collect',return_value=source),patch('china_advertising_midday.http',side_effect=AssertionError('No WB calls')):
   bundle=prepare_midday(IO(),'2026-10-27')
  self.assertEqual([1,2],[c['id'] for c in bundle['campaigns']])
if __name__=='__main__':unittest.main()
