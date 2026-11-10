import unittest
from china_budget_reserve import attach_completed_evidence, apply
from china_advertising_cards import enhance

class InventoryRendering(unittest.TestCase):
    def test_draft_omitted_from_ad_table_remains_in_budget_audit_and_renders(self):
        state=dict(id=99,status=4,currency='CNY',settings=dict(name='Draft',payment_type='cpc',placements=dict(search=True)),timestamps=dict(created='2026-11-09T00:00:00Z',started=None),nm_settings=[])
        source=dict(ids=[99],observed_at='2026-11-10T04:19:00Z',period_from='2026-11-03',period_to='2026-11-09',batches={'0':dict(campaigns=dict(adverts=[state]),stats=[],budgets=dict(adverts=[]))},catalogue=dict(rows=[]),executions=[],config=dict(minTopUp=10000))
        bundle=dict(day='2026-11-10',days=['2026-11-07','2026-11-08','2026-11-09'],campaigns=[])
        attached=apply(attach_completed_evidence(bundle,source,[]))
        result=enhance(attached,source)
        self.assertEqual(result['budget_audit_coverage']['audited_count'],1)
        row=result['campaigns'][0]
        self.assertTrue(row['missing_stats'])
        self.assertIsNone(row['current_period'])
        self.assertIsNone(row['period'])
        self.assertIsNone(row['drr'])
        self.assertIsNone(row['budget_action'])
        self.assertEqual(row['zone'],'поиск')

if __name__=='__main__':unittest.main()

