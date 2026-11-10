import unittest
from china_price_buttons import prepare
class Buttons(unittest.TestCase):
 def test_only_existing_directions(self):
  for rows,modes in [([],[]),([['Повышение']],['all','up']),([['Снижение']],['all','down']),([['Повышение'],['Снижение']],['all','up','down'])]:
   markup,registry=prepare('report',rows,57,'2026-11-10','2026-11-11T00:00:00+03:00')
   if not modes:self.assertIsNone(markup);continue
   self.assertEqual(registry['payload']['allowed_modes'],modes)
   self.assertFalse(registry['payload']['execution_authorized'])
   for row in markup['inline_keyboard']:
    self.assertLessEqual(len(row[0]['callback_data'].encode()),64)
 def test_hash_and_job_change_token(self):
  a=prepare('report',[['Повышение']],57,'2026-11-10','later')[1]
  for answer,jid in [('report2',57),('report',58)]:
   self.assertNotEqual(a['key'],prepare(answer,[['Повышение']],jid,'2026-11-10','later')[1]['key'])
if __name__=='__main__':unittest.main()
