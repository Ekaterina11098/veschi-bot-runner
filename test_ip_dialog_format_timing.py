import unittest
from ip_cloud_dialog import answer_uses_png,stage_durations
class FormatTimingTests(unittest.TestCase):
 def test_boundary(self):
  self.assertFalse(answer_uses_png(307200273,'x'*450));self.assertTrue(answer_uses_png(307200273,'x'*451));self.assertFalse(answer_uses_png(1,'x'*451))
 def test_missing_stages(self):
  self.assertEqual(stage_durations({'received_at':'2026-11-06T05:08:14+00:00'}),{})
