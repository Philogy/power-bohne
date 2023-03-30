import re
import csv
import json
import requests
from collections import Counter, defaultdict
from itertools import groupby
from datetime import datetime
from os import path
from toolz.curried import get

from beancount.ingest.importer import ImporterProtocol
from beancount.core.amount import Amount
from beancount.core.data import new_metadata, Cost, Posting

from ..utils import Transaction, safe_D, FileCache
from .crypto_assets import ASSET_TYPES, AssetType
from ..prices import kraken

import logging

logging.basicConfig(filename='power-bohne-importers.log',
                    format='[%(name)s] %(levelname)s: %(message)s', level=logging.INFO)


KRAKEN_CSV_HEADER =\
    '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"'

KRAKEN_ASSET_REMAP = {
    'XXMR': 'XMR',
    'USDC': 'USDC',
    'XETH': 'ETH',
    'XLTC': 'LTC',
    'XXRP': 'XRP',
    'USDT': 'USDT',
    'ETHW': 'ETHW',
    'DAI': 'DAI',
    'ZEUR': 'EUR',
    'LUNA2': 'LUNA2',
    'NANO': 'NANO',
    'XXDG': 'DOGE',
    'LUNA': 'LUNA'
}


# @dev based off [reedlaw's importer](https://github.com/reedlaw/beancount_kraken)
class Importer(ImporterProtocol):

    def __init__(self, base_currency, cash_acc, net_cash_in, fiat_acc, stables_acc, crypto_acc,
                 withdrawal_fees, crypto_pnl, forex_pnl, kraken_payee='Kraken',
                 log_level=logging.INFO, file_dest_root='exports/kraken', explicit_ignore=None):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)

        self.base_currency = base_currency
        self.cash_acc = cash_acc
        self.net_cash_acc = net_cash_in
        self.fiat_acc = fiat_acc
        self.crypto_acc = crypto_acc
        self.stables_acc = stables_acc
        self.withdrawal_fee_acc = withdrawal_fees
        self.crypto_pnl_acc = crypto_pnl
        self.forex_pnl_acc = forex_pnl
        self.payee = kraken_payee

        self.file_dest_root = file_dest_root
        self.explicit_ignore = set() if explicit_ignore is None else explicit_ignore

        self.unrecognized_assets = defaultdict(int)
        self.sell_price_cache = FileCache('importer.kraken/sell-price.json')

    def name(self) -> str:
        return 'Kraken'

    def identify(self, file) -> bool:
        return bool(
            re.search(r'ledgers.*\.csv', path.basename(file.name))
            and re.match(KRAKEN_CSV_HEADER, file.head())
        )

    def file_account(self, _):
        return self.file_dest_root

    def create_base_posting(self, account, num, meta):
        return Posting(
            account,
            Amount(num, self.base_currency),
            None,
            None,
            None,
            meta
        )

    def create_asset_posting(self, account, asset, asset_amount, base_amount, date, meta,
                             label=None):
        return Posting(
            account,
            Amount(asset_amount, asset),
            Cost(
                base_amount / asset_amount,
                self.base_currency,
                date,
                label
            ),
            None,
            None,
            meta
        )

    def __parse_kraken_asset(self, kraken_asset):
        if (asset := KRAKEN_ASSET_REMAP.get(kraken_asset)) is None:
            self.unrecognized_assets[kraken_asset] += 1
            return kraken_asset
        return asset

    def __get_deposit_postings(self, deposit, meta):
        if (asset := self.__parse_kraken_asset(deposit['asset'])) is None:
            return [], None, False

        amount = safe_D(deposit['amount'])

        if asset == self.base_currency:
            postings = [
                self.create_base_posting(self.net_cash_acc, -amount, meta),
                self.create_base_posting(self.cash_acc, amount, meta)
            ]
            skip = False
        else:
            postings = []
            skip = True

        return postings, 'Deposit', skip

    def get_asset_account(self, asset):
        if (asset_type := ASSET_TYPES.get(asset)) is None:
            self.logger.error(f'No type for asset "{asset}"')
            return None
        if asset_type == AssetType.CRYPTO:
            return self.crypto_acc
        elif asset_type == AssetType.STABLE:
            return self.stables_acc
        elif asset_type == AssetType.FIAT:
            return self.fiat_acc
        else:
            self.logger.error(f'Unrecognized AssetType {asset_type}')

    def get_pnl_account(self, asset):
        if (asset_type := ASSET_TYPES.get(asset)) is None:
            self.logger.error(f'No type for asset "{asset}"')
            return None
        if asset_type == AssetType.FIAT:
            return self.forex_pnl_acc
        elif asset_type in (AssetType.STABLE, AssetType.CRYPTO):
            return self.crypto_pnl_acc
        else:
            self.logger.error(f'Unrecognized AssetType {asset_type}')

    def get_sell_price(self, asset, dt):
        timestamp = int(dt.timestamp())
        pair = f'{asset}{self.base_currency}'
        if (cached_price := self.sell_price_cache[(pair, timestamp)]) is not None:
            return safe_D(cached_price)
        since = timestamp - 150
        trades, errors = kraken.get_trades(pair, since)
        if errors:
            self.logger.error(f'Kraken Trades API returned errors: {errors}')
            return None
        sells = [
            trade
            for trade in trades
            if trade['trade_dir'] == kraken.TradeDirection.Sell
        ]
        if not sells:
            self.logger.error(
                f'Kraken returned no sells for {pair} (since: {since})'
            )
            return None

        best_sell = min(
            sells,
            key=lambda sell: abs(sell['time'].timestamp() - timestamp)
        )
        self.sell_price_cache[(pair, timestamp)] = float(best_sell['price'])
        return best_sell['price']

    def __get_withdrawal_postings(self, withdrawal, meta):
        if (asset := self.__parse_kraken_asset(withdrawal['asset'])) is None:
            return [], None, False

        amount = -safe_D(withdrawal['amount'])
        fee = safe_D(withdrawal['fee'])

        if asset == self.base_currency:
            postings = [
                self.create_base_posting(self.net_cash_acc, amount, meta),
                self.create_base_posting(self.withdrawal_fee_acc, fee, meta),
                self.create_base_posting(self.cash_acc, -amount - fee, meta),
            ]
            skip = False
        else:
            if (price := self.get_sell_price(asset, withdrawal['date'])) is None:
                return [], None, False
            if (pnl_account := self.get_pnl_account(asset)) is None:
                return [], None, False
            if (asset_account := self.get_asset_account(asset)) is None:
                return [], None, False
            postings = [
                Posting(
                    asset_account,
                    Amount(-fee, asset),
                    Cost(None, None, None, None),
                    None,
                    None,
                    meta
                ),
                self.create_base_posting(
                    self.withdrawal_fee_acc, fee * price, meta
                ),
                Posting(pnl_account, None, None, None, None, meta)
            ]
            skip = amount == safe_D('0')

        return postings, 'Withdrawal', skip

    def __get_trade_postings(self, components, meta):
        out_leg, in_leg = components
        if (out_asset := self.__parse_kraken_asset(out_leg['asset'])) is None:
            return [], None, False
        if (in_asset := self.__parse_kraken_asset(in_leg['asset'])) is None:
            return [], None, False
        out_amount = safe_D(out_leg['amount']) - safe_D(out_leg['fee'])
        in_amount = safe_D(in_leg['amount']) - safe_D(in_leg['fee'])
        if self.base_currency not in (in_asset, out_asset):
            self.logger.error(
                f'Non base-currency trade {out_amount} {out_asset} => {in_amount} {in_asset}'
            )
            return [], None, False
        date = components[0]['date'].date()
        if out_asset == self.base_currency:
            if (asset_account := self.get_asset_account(in_asset)) is None:
                return [], None, False

            postings = [
                self.create_base_posting(self.cash_acc, out_amount, meta),
                self.create_asset_posting(
                    asset_account, in_asset, in_amount, -out_amount, date, meta
                )
            ]
        else:
            if (pnl_account := self.get_pnl_account(out_asset)) is None:
                return [], None, False
            if (asset_account := self.get_asset_account(out_asset)) is None:
                return [], None, False
            postings = [
                Posting(
                    asset_account,
                    Amount(out_amount, out_asset),
                    Cost(None, None, None, None),
                    None,
                    None,
                    meta
                ),
                self.create_base_posting(self.cash_acc, in_amount, meta),
                Posting(pnl_account, None, None, None, None, meta)
            ]
        return postings, f'Trade', False

    def mark_potential_income(self, deposit, refid):
        asset = self.__parse_kraken_asset(deposit['asset'])
        self.logger.info(
            f'Potential Income   [{deposit["date"]}] {refid}: {asset:5} {deposit["amount"]}'
        )

    def mark_potential_disposal(self, withdrawal, refid):
        asset = self.__parse_kraken_asset(withdrawal['asset'])
        self.logger.info(
            f'Potential Disposal [{withdrawal["date"]}] {refid}: {asset:5} {withdrawal["amount"]}'
        )

    def extract(self, file, _=None) -> list:

        with open(file.name, 'r', encoding='utf-8') as _file:
            transactions = list(csv.DictReader(_file))

        entries = []

        transactions_by_ref = groupby(transactions, get('refid'))

        missed_types = Counter()

        for refid, transfers in transactions_by_ref:
            if refid in self.explicit_ignore:
                self.logger.debug(f'Skipping {refid}')
                continue

            transfers = list(transfers)
            meta = new_metadata(file.name, None)
            date = datetime.strptime(
                transfers[0]['time'],
                '%Y-%m-%d %H:%M:%S'
            )
            for transfer in transfers:
                transfer['date'] = date
            ttype = transfers[0]['type']

            if ttype == 'deposit':
                if len(transfers) != 1 and not (len(transfers) == 2 and transfers[0]['balance'] == ''):
                    raise Exception(
                        f'Unexpected transfer set: {json.dumps(transfers)}'
                    )
                deposit = transfers[-1]
                self.mark_potential_income(deposit, refid)
                postings, narration, skip = self.__get_deposit_postings(
                    deposit,
                    meta
                )
            elif ttype == 'withdrawal':
                if len(transfers) != 1 and not (len(transfers) == 2 and transfers[0]['balance'] == ''):
                    raise Exception(
                        f'Unexpected transfer set: {json.dumps(transfers)}'
                    )
                withdrawal = transfers[-1]
                self.mark_potential_disposal(withdrawal, refid)
                postings, narration, skip = self.__get_withdrawal_postings(
                    withdrawal,
                    meta
                )
            elif ttype == 'trade':
                postings, narration, skip = self.__get_trade_postings(
                    transfers, meta
                )
            else:
                missed_types[ttype] += 1
                postings = []
                narration = None
                skip = False

            if skip:
                continue

            if narration is None or not postings:
                self.logger.error(f'Failed to process {refid} (type: {ttype})')
                continue

            tx = Transaction(
                new_metadata(file.name, None, {
                    'txref': refid,
                    'time': date.strftime('%H:%M:%S')
                }),
                date.date(),
                '*',  # flag
                self.payee,
                narration,
                frozenset({__name__, 'kraken'}),  # tags
                frozenset(),  # links
                postings
            )
            entries.append(tx)

        for missed_type, instances in missed_types.items():
            self.logger.error(
                f'Unhandled ledger entry type "{missed_type}" (instances: {instances})'
            )

        for asset, instances in self.unrecognized_assets.items():
            self.logger.error(
                f'Unrecognized asset "{asset}" (instances: {instances})'
            )

        self.logger.info(f'Total entries: {len(entries)}')

        self.sell_price_cache.save()

        return entries


if __name__ == '__main__':
    res = requests.get(
        'https://api.kraken.com/0/public/Trades?pair=XMREUR&since=1595840660'
    ).json()
    print(f'res: {res}')
