import re
import csv
import json
from collections import Counter, defaultdict
from itertools import groupby
from datetime import datetime
from os import path
from toolz.curried import get

from beancount.ingest.importer import ImporterProtocol
from beancount.core.amount import Amount
from beancount.core.number import D
from beancount.core.data import EMPTY_SET, new_metadata, Cost, Posting, Price

from ..utils import Transaction, safe_D
from .crypto_assets import ASSET_TYPES


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
    'LUNA2': 'LUNA2'
}


# @dev based off [reedlaw's importer](https://github.com/reedlaw/beancount_kraken)
class Importer(ImporterProtocol):

    def __init__(self, base_currency, cash_acc, net_cash_in, fiat_acc, stables_acc, crypto_acc, withdrawal_fees, crypto_pnl, forex_pnl, kraken_payee='Kraken'):

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

        self.unrecognized_assets = None
        self.uncaught_deposits = None
        self.uncaught_withdrawals = None

    def name(self) -> str:
        return 'Kraken'

    def identify(self, file) -> bool:
        return bool(
            re.match('ledgers.csv', path.basename(file.name))
            and re.match(KRAKEN_CSV_HEADER, file.head())
        )

    def file_account(self, file):
        print('file:', file)
        return 'blobo'

    def create_base_posting(self, account, num, meta):
        return Posting(
            account,
            Amount(num, self.base_currency),
            None,
            None,
            None,
            meta
        )

    def __parse_kraken_asset(self, kraken_asset):
        assert isinstance(self.unrecognized_assets, Counter)
        if (asset := KRAKEN_ASSET_REMAP.get(kraken_asset)) is None:
            self.unrecognized_assets[kraken_asset] += 1
            return None
        return asset

    def __get_deposit_postings(self, deposit, meta):
        if (asset := self.__parse_kraken_asset(deposit['asset'])) is None:
            return [], None

        amount = safe_D(
            deposit['amount'],
            f'{deposit["amount"]!r} not convertible to decimal'
        )

        if asset == self.base_currency:
            postings = [
                self.create_base_posting(self.net_cash_acc, -amount, meta),
                self.create_base_posting(self.cash_acc, amount, meta)
            ]
        else:
            self.uncaught_deposits[asset] += amount
            postings = []

        return postings, 'Deposit'

    def __get_withdrawal_postings(self, withdrawal, meta):
        if (asset := self.__parse_kraken_asset(withdrawal['asset'])) is None:
            return [], None

        amount = -safe_D(
            withdrawal['amount'],
            f'amount {withdrawal["amount"]!r} not convertible to decimal'
        )
        fee = safe_D(
            withdrawal['fee'],
            f'fee {withdrawal["fee"]!r} not convertible to decimal'
        )

        if asset == self.base_currency:
            postings = [
                self.create_base_posting(self.net_cash_acc, amount, meta),
                self.create_base_posting(self.withdrawal_fee_acc, fee, meta),
                self.create_base_posting(self.cash_acc, -amount - fee, meta),
            ]
        else:
            self.uncaught_withdrawals[asset] += amount
            postings = []

        return postings, 'Withdrawal'

    def extract(self, file, _=None) -> list:
        self.unrecognized_assets = Counter()
        self.uncaught_deposits = defaultdict(D)
        self.uncaught_withdrawals = defaultdict(D)

        with open(file.name, 'r', encoding='utf-8') as _file:
            transactions = list(csv.DictReader(_file))

        entries = []

        transactions_by_ref = groupby(transactions, get('refid'))

        missed_types = Counter()

        if missed_types:
            pass

        for refid, transfers in transactions_by_ref:
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
                postings, narration = self.__get_deposit_postings(
                    transfers[-1],
                    meta
                )
            elif ttype == 'withdrawal':
                if len(transfers) != 1 and not (len(transfers) == 2 and transfers[0]['balance'] == ''):
                    raise Exception(
                        f'Unexpected transfer set: {json.dumps(transfers)}'
                    )

                postings, narration = self.__get_withdrawal_postings(
                    transfers[-1],
                    meta
                )

            else:
                missed_types[ttype] += 1
                postings = []
                narration = None

            if narration is None or not postings:
                continue

            tx = Transaction(
                new_metadata(file.name, None, {'txref': refid}),
                date.date(),
                '*',  # flag
                self.payee,
                narration,
                frozenset({'power_bohne.importers/kraken'}),  # tags
                frozenset(),  # links
                postings
            )
            entries.append(tx)

        if missed_types:
            print(';; (ERROR) Unhandled ledger entry types:')
            for ttype, occurrences in missed_types.items():
                s = '' if occurrences == 1 else 's'
                print(f';; - {ttype} ({occurrences} instance{s})')
            print()

        if self.unrecognized_assets:
            print(';; (ERROR) unrecognized assets:', self.unrecognized_assets)
        self.unrecognized_assets = None

        if self.uncaught_deposits:
            print(f';; (INFO) Unhandled deposits:')
            for asset, amount in self.uncaught_deposits.items():
                print(f';; - {asset}: {amount:,}')
            print()
        self.uncaught_deposits = None

        if self.uncaught_withdrawals:
            print(f';; (INFO) Unhandled withdrawals:')
            for asset, amount in self.uncaught_withdrawals.items():
                print(f';; - {asset}: {amount:,}')
            print()
        self.uncaught_withdrawals = None

        return entries
