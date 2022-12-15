from datetime import datetime
from decimal import Decimal
from ..prices.coingecko import get_price_now, get_historic_lin_avg_price
from .vib_utils import Command, CoreCommand, parse_time


def add_gecko_parser(parser):
    parser.add_argument('currency')
    parser.add_argument('coin_id')
    parser.add_argument('-t', '--time')
    parser.add_argument('-p', '--precision', default=6)
    parser.add_argument('-f', '--format', default='%Y-%m-%d %H:%M:%S')
    parser.add_argument('-u', '--utc', action='store_true')


def gecko_cmd(args):
    if args.time is None:
        price = get_price_now(args.coin_id, args.currency)
        time = datetime.now()
        method = 'CURRENT'
    else:
        price, _, _ = get_historic_lin_avg_price(
            args.coin_id,
            args.currency,
            time := parse_time(args.time)
        )
        method = 'LIN_AVG'

    if not isinstance(price, Decimal):
        raise TypeError(f'Resulting price "{price}" not of type Decimal')
    formatted_time = time.strftime(args.format)
    print(
        f'Price of "{args.coin_id}" [{formatted_time}]: {round(price, args.precision)} ({args.precision})'
    )
    print(f'method: {method}')


gecko = Command(
    'gecko',
    dict(),
    CoreCommand(add_gecko_parser, gecko_cmd)
)
