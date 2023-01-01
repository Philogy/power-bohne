import re
import csv
import logging
from datetime import datetime
from collections import namedtuple
from typing import Optional

from beancount.ingest.importer import ImporterProtocol
from beancount.core.data import new_metadata, Posting
from beancount.core.amount import Amount

from ..utils import Transaction, safe_D

logging.basicConfig(filename='power-bohne-importers.log',
                    format='[%(name)s] %(levelname)s: %(message)s', level=logging.INFO)

SPENDING_TRACKER_CSV_HEADER = 'Date, Category, Amount, Note'
DESCRIPTION_FORMAT_PATTERN = r'([^:]+)?:?([^:]+)?>([^:]+)'

Row = namedtuple(
    'Row',
    ['date', 'category', 'amount', 'payee', 'narration', 'fund_source', 'note']
)


class Importer(ImporterProtocol):
    def __init__(self, base_currency, category_accounts: dict[str, str], source_accounts: dict[str, str],
                 file_dest_root='exports/mobile-spending-tracker', log_level=logging.INFO):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)

        self.base_currency = base_currency
        self.category_accounts = category_accounts
        self.source_accounts = source_accounts
        self.file_dest_root = file_dest_root

    def name(self) -> str:
        return 'MobileSpendingTracker'

    def identify(self, file) -> bool:
        return bool(re.match(SPENDING_TRACKER_CSV_HEADER, file.head()))

    def file_account(self, _):
        return self.file_dest_root

    def _parse_row(self, raw_row) -> Row:
        date = datetime.strptime(raw_row['Date'], '%m/%d/%Y').date()
        note = raw_row[' Note']
        category = raw_row[' Category'].strip()
        if not (m := re.match(DESCRIPTION_FORMAT_PATTERN, note)):
            raise Exception(f'Failed to parse note {note!r}')

        payee, narration, fund_source = m.groups()

        if isinstance(narration, str):
            narration = narration.strip()

        row = Row(
            date,
            category,
            safe_D(raw_row[' Amount'].strip()),
            payee.strip(),
            narration,
            fund_source.strip(),
            note
        )
        return row

    def _row_to_tx(self, row: Row, file):
        meta = new_metadata(file.name, None)

        main_account = self.category_accounts.get(row.category)
        if main_account is None:
            self.logger.error(
                f'No account found for category {row.category!r}'
            )
            return None

        main_posting = Posting(
            main_account,
            Amount(-row.amount, self.base_currency),
            None,
            None,
            None,
            meta
        )

        snd_account = self.source_accounts.get(row.fund_source)
        if snd_account is None:
            self.logger.error(
                f'No account found for fund source {row.fund_source!r}'
            )
            return None

        snd_posting = Posting(
            snd_account,
            Amount(row.amount, self.base_currency),
            None,
            None,
            None,
            meta
        )

        return Transaction(
            new_metadata(file.name, None, {'note': row.note.strip()}),
            row.date,
            '*',
            row.payee,
            row.narration,
            frozenset({__name__}),
            frozenset(),
            [main_posting, snd_posting]
            if row.amount > 0
            else [snd_posting, main_posting]


        )

    def extract(self, file, _=None) -> list:
        try:
            with open(file.name, 'r', encoding='utf-8') as f:
                rows = list(map(self._parse_row, csv.DictReader(f)))
            return list(map(lambda row: self._row_to_tx(row, file), rows))
        except Exception as err:
            self.logger.error('Exception', exc_info=err)
