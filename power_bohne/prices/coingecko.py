import requests
from decimal import Decimal
from datetime import datetime
from collections import namedtuple
import json

COINGECKO_BASE = 'https://api.coingecko.com/api/'


def get(endpoint, params={}, parse_int=None, **kwarg_params):
    res = requests.get(
        f'{COINGECKO_BASE}/{endpoint}',
        {**params, **kwarg_params}
    )
    return json.loads(res.text, parse_float=Decimal, parse_int=parse_int)


def _validate_single_gecko_input(f):
    def gecko_fn(coin_id, vs_currency, *args, **kwargs):
        assert ',' not in coin_id, 'Provide single, unseparated'
        assert ',' not in vs_currency, 'Provide single, unseparated'
        return f(coin_id, vs_currency, *args, **kwargs)
    return gecko_fn


@_validate_single_gecko_input
def get_price_now(coin_id, vs_currency):
    res = get(
        'v3/simple/price',
        ids=coin_id,
        vs_currencies=vs_currency
    )
    return res.get(coin_id, dict()).get(vs_currency)


Price = namedtuple('Price', ['price', 'time'])


@_validate_single_gecko_input
def get_price_over_range(coin_id, vs_currency, start, end):
    res = get(f'v3/coins/{coin_id}/market_chart/range', {
        'vs_currency': vs_currency,
        'from': start,
        'to': end
    }, parse_int=int)
    return [
        Price(price, datetime.fromtimestamp(timestamp / 1000))
        for timestamp, price in res.get('prices')
    ]


HISTORIC_LIN_RADIUS = 5 * 24 * 60 * 60


def get_historic_lin_avg_price(coin_id, vs_currency, timestamp):
    prices = get_price_over_range(
        coin_id,
        vs_currency,
        timestamp - HISTORIC_LIN_RADIUS,
        timestamp + HISTORIC_LIN_RADIUS
    )
    target = datetime.fromtimestamp(timestamp)

    # do binary search
    left = 0
    right = len(prices) - 1

    while left <= right:
        mid = left + (right - left) // 2
        if prices[mid].time < target:
            left = mid + 1
        elif prices[mid].time > target:
            right = mid - 1
        else:
            # target found in list
            return prices[mid].price, 0, 0

    # The target is not in the list.
    # Find the closest higher and lower numbers.
    if left == 0 or right == len(prices) - 1:
        return None, None, None
    else:
        p1, t1 = prices[right]
        p2, t2 = prices[left]
        t1 = Decimal(t1.timestamp())
        t2 = Decimal(t2.timestamp())
        t = Decimal(timestamp)

        return ((t - t1) * (p2 - p1) / (t2 - t1) + p1, float(t1 - t), float(t2 - t))


if __name__ == '__main__':
    target = datetime.now().timestamp() - 2 * 365 * 24 * 60 * 60
    print(f'datetime.fromtimestamp(target): {datetime.fromtimestamp(target)}')
    price, d1, d2 = get_historic_lin_avg_price('ethereum', 'eur', target)
    print(f'price: {price}')
    print(f'd1: {d1}')
    print(f'd2: {d2}')
