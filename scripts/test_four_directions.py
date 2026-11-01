import unittest, copy
from unittest.mock import patch
from china_advertising_directions import attach, addition_shortlist, overview, campaign_table
from china_advertising_growth import merge
from china_advertising_v2 import include_archived, build

class FourDirectionTests(unittest.TestCase):

    def test_recommendations_stay_grouped_by_actual_campaign(self):
        bundle = dict(campaigns=[dict(id=1, status=9), dict(id=2, status=7)], recommendation_directions={'add': dict(rows=[dict(article='new', campaign_id=1, target_minor=28, bid_verified=True)]), 'reduce': dict(rows=[dict(article='existing', campaign_id=1, action=dict(old_minor=31, target_minor=28))])})
        out = campaign_table(bundle)
        self.assertEqual(len(out['campaigns']), 2)
        self.assertEqual(len(out['campaigns'][0]['direction_recommendations']), 2)
        self.assertEqual(out['campaigns'][1]['direction_recommendations'], ['Не запускать.'])
        self.assertEqual(out['campaigns'][0]['direction_recommendations'][0], 'new: Добавить · ставка 0.28 CNY.')
        bundle['recommendation_directions']['add']['rows'][0]['bid_verified'] = False
        self.assertEqual(len(campaign_table(bundle)['campaigns'][0]['direction_recommendations']), 1)

    def test_brief_png_retains_only_page_bound_ready_actions(self):
        from PIL import ImageDraw
        action = dict(kind='ad_set_bid', old_minor=31, target_minor=28)
        bundle = dict(source_observed_at='02.11.2026', recommendation_directions={k: dict(label=k, count=0, status='checked', note='INTERNAL_DIAGNOSTIC', rows=[]) for k in ['raise', 'add', 'reduce', 'exclude']})
        bundle['recommendation_directions']['reduce']['rows'] = [dict(article='423', campaign_id=12, action=action, ready=True, decision='INTERNAL_DIAGNOSTIC')]
        captured = []
        original = ImageDraw.ImageDraw.text

        def text(draw, xy, value, *a, **kw):
            captured.append(str(value))
            return original(draw, xy, value, *a, **kw)
        with patch.object(ImageDraw.ImageDraw, 'text', text):
            files = overview(bundle)
        self.assertEqual(files[0]['actions'], [action])
        self.assertNotIn('INTERNAL_DIAGNOSTIC', ' '.join(captured))
        self.assertEqual(len(files), 1)

    def test_archive_totals_and_missing_not_zero(self):
        cs = [dict(id=1, status=9, focus=[]), dict(id=2, status=7, focus=[], period=dict(spend=7, amount=0, orders=0)), dict(id=3, status=7, focus=[], period=None, missing_stats=True)]
        out = attach(dict(campaigns=cs), dict(catalogue=dict(rows=[])))
        self.assertEqual(set(out['recommendation_directions']), {'raise', 'add', 'reduce', 'exclude'})
        self.assertEqual(out['archive_expenses']['totals']['spend'], 7)
        self.assertEqual(out['archive_expenses']['missing_stats_ids'], [3])
        self.assertFalse(out['archive_expenses']['complete'])
        self.assertEqual(out['recommendation_directions']['add']['status'], 'unavailable')

    def test_raise_survives_focus_pipeline(self):
        a = dict(kind='ad_set_bid', direction='raise', campaign_id=1, nm_id=2, article='2-Test', old_minor=28, target_minor=31, growth_evidence=dict(metrics=dict(spend=3, amount=200, orders=5, clicks=100), decision_days=['2026-10-30', '2026-10-31']))
        out = merge(dict(campaigns=[dict(id=1, status=9, balance=1, attention=[], focus=[dict(nm=2, action=None)])]), [a])
        self.assertEqual(out['campaigns'][0]['focus'][0]['action'], a)
        report = attach(out, dict(catalogue=dict(rows=[])))
        self.assertEqual(report['recommendation_directions']['raise']['count'], 1)

    def test_four_types_and_addition_not_executable(self):
        rows = [dict(nm=1, article='1', decision='raise', action=dict(kind='ad_set_bid', old_minor=28, target_minor=31)), dict(nm=2, article='2', decision='reduce', action=dict(kind='ad_set_bid', old_minor=31, target_minor=28)), dict(nm=3, article='3', decision='exclude', action=dict(kind='ad_exclude_sku'))]
        s = dict(catalogue=dict(rows=[dict(nmID=4, vendorCode='4')]), addition_scan=dict(status='complete', period_from='2026-10-01', period_to='2026-10-31', candidate_ids=[4]), economics=dict(rows={'4': dict(expected_margin_before_ads_cny=20, stock_free=10, sample_size=10)}))
        out = attach(dict(campaigns=[dict(id=10, status=9, focus=rows)]), s)
        self.assertEqual([r['count'] for r in out['recommendation_directions'].values()], [1, 1, 1, 1])
        self.assertFalse(out['recommendation_directions']['add']['rows'][0]['ready'])

    def test_archived_collection_does_not_read_budget_or_drop_cpm(self):
        s = dict(period_from='2026-10-29', period_to='2026-10-31', ids=[1], batches={'0': dict(campaigns=dict(adverts=[dict(id=1, status=9)]), stats=[], budgets=dict(adverts=[]))})

        class IO:

            def get(self, k):
                return None

            def create(self, k, v):
                return True
        calls = []

        def read(io, path, method='GET', body=None):
            calls.append(path)
            if path == '/adv/v1/promotion/count':
                return dict(adverts=[dict(status=7, advert_list=[dict(advertId=2)])])
            if path.startswith('/api/advert/v2/adverts'):
                return dict(adverts=[dict(id=2, status=7)])
            return [dict(advertId=2, sum=3)]
        with patch('china_advertising_v2.http', read):
            out = include_archived(IO(), s, '2026-11-01')
        self.assertEqual(out['ids'], [1, 2])
        self.assertFalse(any(('budget' in c for c in calls)))
        self.assertEqual(out['batches']['archive:2']['stats'][0]['sum'], 3)
if __name__ == '__main__':
    unittest.main()
