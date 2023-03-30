import requests
from datetime import datetime
from decimal import Decimal
from enum import Enum


class TradeDirection(Enum):
    Buy = 1
    Sell = 2


class OrderType(Enum):
    Limit = 1
    Market = 2


def to_trade_dir(trade_dir_char):
    assert trade_dir_char in {'b', 's'}
    if trade_dir_char == 'b':
        return TradeDirection.Buy
    return TradeDirection.Sell


def to_order_type(order_type_char):
    assert order_type_char in {'m', 'l'}
    if order_type_char == 'm':
        return OrderType.Market
    return OrderType.Limit


def get_trades(pair, since=None):
    raw_res = requests.get('https://api.kraken.com/0/public/Trades', {
        'pair': pair,
        'since': since
    }).json()
    if 'result' not in raw_res:
        print(f'pair: {pair}')
        print(f'raw_res: {raw_res}')
    results = next(iter(raw_res['result'].values()))
    return [
        {
            'price': Decimal(price),
            'volume': Decimal(volume),
            'time': datetime.fromtimestamp(timestamp),
            'trade_dir': to_trade_dir(buy_sell),
            'order_type': to_order_type(market_limit),
            'misc': misc,
            'trade_id': trade_id
        }
        for price, volume, timestamp, buy_sell, market_limit, misc, trade_id in results
    ], raw_res['error']


if __name__ == '__main__':
    trades, _ = get_trades('XBTUSD', since=1595840660)
    print(f'trades: {trades}')
