from datetime import datetime
from decimal import Decimal
from ..prices.coingecko import get_price_now, get_historic_lin_avg_price, get_ticker
from .vib_utils import Command, CoreCommand, parse_time


def add_gecko_parser(parser):
    parser.add_argument('currency')
    parser.add_argument('coin_id')
    parser.add_argument('-t', '--time')
    parser.add_argument('-c', '--precision-currency', default=3, type=int)
    parser.add_argument('-k', '--precision-units', default=6, type=int)
    parser.add_argument('-f', '--format', default='%Y-%m-%d %H:%M:%S')
    parser.add_argument('-u', '--utc', action='store_true')
    parser.add_argument('-v', '--value')
    parser.add_argument('-a', '--amount')


def gecko_cmd(args):
    if args.time is None:
        price = get_price_now(args.coin_id, args.currency)
        time = datetime.now()
        method = 'CURRENT'
    else:
        price, before, after = get_historic_lin_avg_price(
            args.coin_id,
            args.currency,
            time := parse_time(args.time)
        )
        method = f'LIN_AVG ({before / 60:,.2f} min | +{after / 60:,.2f} min)'

    if not isinstance(price, Decimal):
        raise TypeError(f'Resulting price "{price}" not of type Decimal')
    formatted_time = time.strftime(args.format)
    currency = args.currency.upper()
    def round_currency(x): return round(x, args.precision_currency)
    def round_units(x): return round(x, args.precision_units)
    ticker = get_ticker(args.coin_id)
    print(
        f'Price of "{args.coin_id}" [{formatted_time}] (1 {ticker}): {round_currency(price):,} {currency}'
    )
    if args.value is not None:
        value = Decimal(args.value)
        amount = value / price
        print(
            f'Amount ({round_currency(value):,} {currency}): {round_units(amount):,} {ticker}'
        )
    if args.amount is not None:
        amount = Decimal(args.amount)
        value = amount * price
        print(
            f'Value ({round_units(amount):,} {ticker}): {round_currency(value):,} {currency}'
        )
    print(f'method: {method}')


gecko = Command(
    'gecko',
    dict(),
    CoreCommand(add_gecko_parser, gecko_cmd)
)
