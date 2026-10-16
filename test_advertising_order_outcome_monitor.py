import unittest
from datetime import datetime,timedelta,timezone
from advertising_order_outcome_monitor import ingest,plan,seed,financial_revision
NOW=datetime(2026,10,16,17,tzinfo=timezone.utc)
def observation(day='2026-10-08',**changes):
 row=dict(gnumber='a',nm_id=1123677454,order_dt=day+' 10:00:00',sale_dt=None,refund_dt=None,billed_times=0,refunded_times=0,is_canceled_order=0,backlogistic_times=0,confirmed=0,forward_logistic_rub=0,backward_logistic_rub=0);row.update(changes)
 return dict(tool='lk_wb_card_orders',status='received',scope_verified=True,observed_at=NOW.isoformat(),arguments=dict(type='products',value='139147637',date_from=day,date_to=day,start_row=0,end_row=300),
 data=dict(total=1,data=[row],filterModel=dict(product_id=dict(filter=139147637),order_dt=dict(dateFrom=day,dateTo=day))))
class MonitorTests(unittest.TestCase):
 def test_old_unresolved_date_rechecked(self):
  s=ingest({},observation(),1);self.assertEqual(plan(s,NOW+timedelta(days=1))[0]['arguments']['date_from'],'2026-10-08')
 def test_fresh_not_repeated(self):self.assertEqual(plan(ingest({},observation(),1),NOW+timedelta(hours=23)),[])
 def test_recent_buyout_kept_active(self):
  s=ingest({},observation(sale_dt='2026-10-15 12:00:00',billed_times=1),1);self.assertTrue(s['orders']['a']['active'])
 def test_late_return_reopens_and_preserves_history(self):
  o=observation(sale_dt='2026-10-10 12:00:00',billed_times=1);s=ingest({},o,1);o['observed_at']=(NOW+timedelta(days=1)).isoformat();o['data']['data'][0].update(refund_dt='2026-10-17 12:00:00',refunded_times=1);s=ingest(s,o,2)
  self.assertEqual(s['orders']['a']['status'],'returned');self.assertEqual(len(s['history']),2);self.assertIsNone(s['orders']['a']['mature_retention_ratio'])
 def test_partial_keeps_prior(self):
  o=observation();s=ingest({},o,1);o['data']['total']=2
  with self.assertRaises(ValueError):ingest(s,o,2)
  self.assertEqual(s['orders']['a']['snapshot_id'],1)
 def test_omitted_order_blocks(self):
  s=ingest({},observation(),1);o=observation();o['data'].update(total=0,data=[])
  with self.assertRaises(ValueError):ingest(s,o,2)
 def test_scope_invalid(self):
  o=observation();o['data']['filterModel']['product_id']['filter']=1
  with self.assertRaises(ValueError):ingest({},o,1)
 def test_zero_failure_not_closed(self):
  o=observation(is_canceled_order=1,confirmed=1);s=ingest({},o,1);o['observed_at']=(NOW+timedelta(days=40)).isoformat();s=ingest(s,o,2);self.assertTrue(s['orders']['a']['active'])
 def test_long_pending_weekly(self):
  s=ingest({},observation(day='2026-09-01'),1);self.assertEqual(s['orders']['a']['monitoring_state'],'weekly_unresolved');self.assertEqual(plan(s,NOW+timedelta(days=1)),[])
 def test_archived_not_final_and_explicit_incident(self):
  o=observation(sale_dt='2026-09-01 12:00:00',billed_times=1);s=ingest({},o,1);o['observed_at']=(NOW+timedelta(days=15)).isoformat();s=ingest(s,o,2)
  self.assertFalse(s['orders']['a']['active']);self.assertFalse(s['orders']['a']['financially_final']);self.assertEqual(len(plan(s,NOW+timedelta(days=16),incident_order_ids=('a',))),1)
 def test_request_bound(self):
  s={'orders':{}}
  for n in range(6):
   o=observation(day='2026-10-'+str(n*2+1).zfill(2));o['data']['data'][0]['gnumber']=str(n);s=ingest(s,o,n)
  self.assertEqual(len(plan(s,NOW+timedelta(days=10),max_requests=4)),4)
 def test_changed_finance_reopens_only_known_sku(self):
  s=ingest({},observation(),1);s['orders']['a']['active']=False
  o=dict(tool='lk_wb_products',status='received',arguments=dict(date_from='2026-10-15'),data=dict(data=dict(need_update=0,total=1,data=[dict(nm_id=1123677454,logistic_all=10)])))
  s=financial_revision(s,o,NOW);self.assertFalse(s['orders']['a']['active'])
  o['data']['data']['data'][0]['logistic_all']=20;s=financial_revision(s,o,NOW)
  self.assertTrue(s['orders']['a']['active']);self.assertIsNone(s['orders']['a']['mature_retention_ratio'])
 def test_unchanged_finance_does_not_reopen(self):
  s=ingest({},observation(),1);s['orders']['a']['active']=False
  o=dict(tool='lk_wb_products',status='received',arguments=dict(date_from='2026-10-15'),data=dict(data=dict(need_update=0,total=1,data=[dict(nm_id=1123677454,logistic_all=10)])))
  s=financial_revision(s,o,NOW);s=financial_revision(s,o,NOW)
  self.assertFalse(s['orders']['a']['active'])
 def test_seed_old_unresolved_and_recent_buyout_without_source_calls(self):
  now=datetime.now(timezone.utc)
  rows=[dict(srid='u',gNumber='u',nmId=1123677454,date=(now-timedelta(days=20)).isoformat(),isCancel=False),dict(srid='s',gNumber='s',nmId=320248210,date=(now-timedelta(days=20)).isoformat(),isCancel=False)]
  ledger=dict(status='complete',older_order_rows=rows,matching_sales=[dict(id=1,collected_at=now.isoformat(),rows=[dict(saleID='S1',srid='s',date=(now-timedelta(days=2)).isoformat())])])
  s=seed({},dict(older_sales_ledger_audit_20261016=ledger))
  self.assertEqual(set(s['orders']),{'u','s'});self.assertEqual(s['orders']['s']['status'],'buyout');self.assertIsNone(s['orders']['s']['mature_retention_ratio'])
 def test_old_seed_never_overwrites_newer_observation(self):
  now=datetime.now(timezone.utc)
  s=ingest({},observation(),1)
  ledger=dict(status='complete',older_order_rows=[dict(srid='old',gNumber='a',nmId=1123677454,date=(now-timedelta(days=20)).isoformat(),isCancel=False)],matching_sales=[dict(id=3,collected_at=(now-timedelta(days=5)).isoformat(),rows=[])])
  updated=seed(s,dict(older_sales_ledger_audit_20261016=ledger));self.assertEqual(updated['orders']['a']['snapshot_id'],1)
if __name__=='__main__':unittest.main()
