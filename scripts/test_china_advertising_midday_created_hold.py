import unittest
from unittest.mock import patch
from china_midday_completed_review import completed_campaign_stats
class FirstFullDayHistory(unittest.TestCase):
 def state(self,created):return dict(id=41756218,status=9,timestamps=dict(created=created))
 def test_recent_campaign_unknown_history_is_not_zero(self):
  unknown={}
  with patch('china_midday_completed_review.http',return_value={}):
   got=completed_campaign_stats(None,[self.state('2026-11-10T15:45:15+03:00')],{},'2026-11-04','2026-11-10',pending_unknown=unknown)
  self.assertNotIn(41756218,got)
  self.assertEqual('unavailable_not_zero',unknown[41756218]['statistics_status'])
 def test_old_campaign_still_requires_history(self):
  with patch('china_midday_completed_review.http',return_value={}):
   with self.assertRaisesRegex(ValueError,'history unavailable'):
    completed_campaign_stats(None,[self.state('2026-11-09T15:45:15+03:00')],{},'2026-11-04','2026-11-10',pending_unknown={})
 def test_timezone_required(self):
  with patch('china_midday_completed_review.http',return_value={}):
   with self.assertRaises(ValueError):
    completed_campaign_stats(None,[self.state('2026-11-10T15:45:15')],{},'2026-11-04','2026-11-10',pending_unknown={})
 def test_known_actual_history_kept(self):
  actual=dict(advertId=41756218,days=[dict(date='2026-11-10',sum=9)])
  unknown={}
  with patch('china_midday_completed_review.http',return_value=[actual]):
   got=completed_campaign_stats(None,[self.state('2026-11-10T15:45:15+03:00')],{},'2026-11-04','2026-11-10',pending_unknown=unknown)
  self.assertEqual(actual,got[41756218]);self.assertEqual({},unknown)
if __name__=='__main__':unittest.main()
