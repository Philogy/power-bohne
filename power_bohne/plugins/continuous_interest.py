from typing import NamedTuple, Optional
from beancount.core.data import Open, Amount, Posting, Transaction
from beancount.core.number import Decimal
from datetime import date
from ..utils import PluginError


class InterestAccount:
    account: str
    last_updated: date
    balance: Decimal
    currency: str
    interest_rate: Decimal
    expense_account: str
    income_account: str

    def __init__(
        self,
        account: str,
        last_updated: date,
        currency: str,
        interest_rate: Decimal,
        expense_account: str,
        income_account: str,
    ) -> None:
        self.account = account
        self.last_updated = last_updated
        self.balance = Decimal('0')
        self.currency = currency
        self.interest_rate = interest_rate
        self.expense_account = expense_account
        self.income_account = income_account

    def update_account(self, d: date, post: Posting) -> tuple[Amount, str]:
        assert post.account == self.account, f'Invalid posting {post} for account {self.account}'
        assert self.currency == post.units.currency, \
            f'Account posting currency mismatch {self.currency} != {post.units.currency}'
        assert post.units.number is not None, f'Post units number is None: {post}'

        amount = post.units.number

        time_passed = d - self.last_updated

        growth_rate = Decimal(1) + self.interest_rate
        bal_grow = growth_rate ** Decimal(time_passed.days / 365)

        new_bal = self.balance * bal_grow
        interest = new_bal - self.balance
        self.balance = new_bal + amount
        self.last_updated = d

        if self.balance >= 0:
            interest_source_account = self.income_account
        else:
            interest_source_account = self.expense_account

        return Amount(interest, self.currency), interest_source_account


_NAMESPACE = 'interest'

RATE_FIELD = f'{_NAMESPACE}-rate'
EXPENSE_FIELD = f'{_NAMESPACE}-expense'
INCOME_FIELD = f'{_NAMESPACE}-income'
FIELDS = [RATE_FIELD, EXPENSE_FIELD, INCOME_FIELD]


def continuous_interest_core(entries, options_map, raw_config=None):
    errors = []
    if (operating_currencies := options_map.get('operating_currency')) is None or len(operating_currencies) != 1:
        errors.append(PluginError(
            f'Must have exactly 1 operating currency for continuous interest plugin',
            options_map['filename']
        ))
    if len(operating_currencies) == 0:
        return entries, errors

    currency: str = operating_currencies[0]
    assert isinstance(currency, str)
    interest_accounts: dict[str, InterestAccount] = {}
    for entry in entries:
        with PluginError.capture_assert(errors, entry=entry):
            if isinstance(entry, Open):
                meta = entry.meta
                field_count = sum([
                    f in meta
                    for f in FIELDS
                ])
                if field_count == 0:
                    continue
                assert field_count == len(FIELDS), \
                    'Entry contains some but not all necessary interest fields'
                interest_account = entry.account
                assert interest_account not in interest_accounts, f'Redefining interest account {interest_account}'
                rate = entry.meta[RATE_FIELD]
                assert isinstance(rate, Amount), \
                    f'{RATE_FIELD} must be of type Amount'
                assert rate.currency == 'PERCENT', f'Unsupported unit "{rate.currency}"'
                assert rate.number is not None, f'Empty number in rate {rate}'

                interest_accounts[interest_account] = InterestAccount(
                    interest_account,
                    entry.date,
                    currency,
                    rate.number * Decimal('0.01'),
                    entry.meta[EXPENSE_FIELD],
                    entry.meta[INCOME_FIELD]
                )
            elif isinstance(entry, Transaction):
                new_postings: list[Posting] = []
                for post in entry.postings:
                    if (acc := interest_accounts.get(post.account)) is None:
                        continue
                    interest, src_account = acc.update_account(
                        entry.date,
                        post
                    )
                    new_postings.extend([
                        Posting(post.account, interest,
                                None, None, None, None),
                        Posting(src_account, -interest, None, None, None, None)
                    ])
                entry.postings.extend(new_postings)

    return entries, errors


__plugins__ = ['continuous_interest_core']
