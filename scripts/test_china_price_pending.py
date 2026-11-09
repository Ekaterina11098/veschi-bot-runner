import unittest
from datetime import datetime,timezone
from china_price_pending import reconcile

class PendingTests(unittest.TestCase):
    def setUp(self):
        self.state={'pending_notice':{'job_id':163,'answer':'obsolete'},'price_history':{'x':1}}
        self.now=datetime.now(timezone.utc)
    def run_case(self,**fields):
        row=dict(id=163,status='failed',error='cancelled_by_owner: obsolete',lease_until=None);row.update(fields)
        return reconcile(self.state,lambda t,p:[row],self.now)
    def test_cancelled_retires_without_delivery_and_keeps_history(self):
        result=self.run_case()
        self.assertNotIn('pending_notice',result)
        self.assertEqual(result['price_history'],self.state['price_history'])
        self.assertFalse(result['retired_cancelled_notices']['163']['delivered'])
        self.assertIn('pending_notice',self.state)
    def test_live_failed_uncertain_and_leased_remain_blocking(self):
        for fields in ({'status':'pending'},{'status':'running'},{'error':'Telegram delivery uncertain'},
                       {'error':'worker failed'},{'lease_until':'2026-11-09T20:00:00Z'},{'id':175}):
            with self.subTest(fields=fields):self.assertEqual(self.run_case(**fields),self.state)
    def test_missing_job_never_clears(self):
        self.assertEqual(reconcile(self.state,lambda t,p:[],self.now),self.state)

if __name__=='__main__':unittest.main()

