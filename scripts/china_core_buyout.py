"""Isolated China agent foundation; no network or WB mutation capabilities."""
import json
from decimal import Decimal, ROUND_CEILING
from pathlib import Path


def load_profile():
    return json.loads(Path(__file__).with_name('profile.json').read_text(encoding='utf-8'))


def build_context(records=(), history=()):
    """Accept only explicitly scoped China data, including conversation history."""
    records, history = list(records), list(history)
    for item in records + history:
        if item.get('cabinet') != 'token_3':
            raise ValueError('China context requires explicit token_3 cabinet')
    return {'profile': load_profile(), 'records': records, 'history': history,
            'tools': [], 'write_enabled': False}


def forecast_price(cost_rub, delivery_rub_per_order, *, buyout_stats):
    """Reproduce the agreed scenario; delivery is mandatory, never guessed."""
    def number(value):
        if value is None or isinstance(value, bool):
            raise ValueError('Missing or invalid scenario input')
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise ValueError('Invalid scenario input')
        return result
    cost, delivery = number(cost_rub), number(delivery_rub_per_order)
    if cost == 0:
        raise ValueError('COGS must be known and positive')
    profile = load_profile()
    params = profile['economics']['parameters']
    p = lambda key: Decimal(str(params[key]['value']))
    from .expected_order_profit import buyout_from_product
    resolved = buyout_from_product(buyout_stats)
    buyout, rate = resolved['probability'], p('rub_per_cny')
    params['buyout_rate'] = dict(value=float(buyout), source=resolved['source'], sample_size=resolved['sample_size'], note=resolved['note'])
    retained = 1 - p('commission_rate') - p('acquiring_rate')
    if not 0 < buyout <= 1 or rate <= 0 or retained <= 0:
        raise ValueError('Invalid scenario parameters')
    price = ((cost * (1 + p('target_profit_on_cost')) +
              (delivery + p('acceptance_rub_per_dispatch')) / buyout) /
             retained / rate).quantize(Decimal('1'), rounding=ROUND_CEILING)
    return {'cabinet': 'token_3', 'model_version': profile['economics']['model_version'],
            'seller_price_after_discount_cny': int(price),
            'status': 'forecast_not_actual_profit', 'write_enabled': False,
            'parameters': params, 'unresolved': profile['economics']['unresolved']}
