from .utils import parse_config, get_account_booking_methods, PluginError
from beancount.core import amount, position
from beancount.core.data import Booking, Transaction, Posting
from beancount.core.number import D
from beancount.core.getters import get_entry_accounts
from toolz import curry, compose
from functools import reduce


def validate_config(entries, options_map, raw_config):
    if raw_config is None:
        return None, [PluginError('InvalidConfig: Config empty', options_map['filename'])]

    try:
        config = parse_config(raw_config)
    except:
        return None, [PluginError('InvalidConfig: Faile to parse config, expected: "<key1>=<value1> <key2>=<value2> <list_key>=<item1_1>,<item1_2>,"', filename=options_map['filename'])]

    for required_key in 'st', 'lt', 'unk',  'acc':
        if required_key not in config:
            return None, [PluginError(f'InvalidConfig: Missing key \'{required_key}\' required', options_map['filename'])]

    if not isinstance(config['acc'], list):
        return None, [PluginError(f'InvalidConfig: \'acc\' must be list, use trailling comma if single item', options_map['filename'])]

    accounts_booking = get_account_booking_methods(entries)
    for account in config['st'], config['lt'], config['unk'], *config['acc']:
        if account not in accounts_booking:
            return None, [PluginError(f'NonexistentAccount: account \'{account}\' not found', filename=options_map['filename'])]

    for asset_account in config['acc']:
        if (method := accounts_booking[asset_account]) != Booking.FIFO:
            return None, [PluginError(f'InvalidBookingMethod: \'{asset_account}\' using "{method}" instead of FIFO', filename=options_map['filename'])]

    return config, []


def calc_value(position):
    return amount.Amount(position.cost.number * position.units.number, position.cost.currency)


def sum_amounts(amounts, currency):
    return reduce(
        amount.add,
        amounts,
        amount.Amount(D(0), currency)
    )


def sum_posting_units(postings, currency):
    return sum_amounts(map(lambda p: p.units, postings), currency)


def calc_total_value(postings, currency):
    return sum_amounts(map(compose(calc_value, position.get_position), postings), currency)


def get_pnl(postings, sub_postings, total_net_gain):
    asset_currency = postings[0].units.currency
    base_currency = total_net_gain.currency
    total_units = sum_posting_units(postings, asset_currency).number
    total_value = calc_total_value(postings, base_currency).number
    sub_units = sum_posting_units(sub_postings, asset_currency).number
    sub_value = calc_total_value(sub_postings, base_currency).number

    return amount.Amount(
        (total_net_gain.number + total_value) *
        sub_units / total_units - sub_value,
        base_currency
    )


def validate_asset_postings(asset_postings, tx):
    asset_currency = asset_postings[0].units.currency
    for asset_posting in asset_postings:
        error_loc_args = asset_posting.meta['filename'], asset_posting.meta['lineno'], tx
        currency = asset_posting.units.currency
        if asset_currency != currency:
            return PluginError(
                f'CurrencyMismatch: "{currency}" != "{asset_currency}"',
                *error_loc_args
            )
        if asset_posting.units.number >= 0:
            return PluginError(f'InvalidPosting: Not disposal', *error_loc_args)

    return None


@curry
def tx_separator(unclassified, crypto_assets_accounts, tx):
    asset_postings = []
    value_out_postings = []
    net_gain_value = None

    for posting in tx.postings:
        if posting.account in crypto_assets_accounts:
            asset_postings.append(posting)
        elif posting.account == unclassified:
            if net_gain_value is not None:
                error = PluginError(
                    'InvalidPosting: Duplicate unclassified posting',
                    posting.meta['filename'], posting.meta['lineno'], tx
                )
                return None, None, error
            net_gain_value = posting.units
        else:
            value_out_postings.append(posting)

    if validation_error := validate_asset_postings(asset_postings, tx):
        return None, None, validation_error

    long_term_postings = []
    short_term_postings = []
    for asset_posting in asset_postings:
        if (tx.date - asset_posting.cost.date).days >= 365:
            long_term_postings.append(asset_posting)
        else:
            short_term_postings.append(asset_posting)

    lt_pnl = get_pnl(asset_postings, long_term_postings, net_gain_value)
    st_pnl = get_pnl(asset_postings, short_term_postings, net_gain_value)

    return st_pnl, lt_pnl, None


def insert_pnls(entry, st_pnl, lt_pnl, config):
    short_term_pnl_acc = config['st']
    long_term_pnl_acc = config['lt']
    unclassified = config['unk']

    new_postings = []
    unclassified_posting = None
    for posting in entry.postings:
        if posting.account == unclassified:
            unclassified_posting = posting
        else:
            new_postings.append(posting)

    assert unclassified_posting is not None

    if st_pnl.number != 0:
        new_postings.append(Posting(
            short_term_pnl_acc,
            st_pnl,
            None,
            None,
            unclassified_posting.flag,
            unclassified_posting.meta
        ))

    if lt_pnl.number != 0:
        new_postings.append(Posting(
            long_term_pnl_acc,
            lt_pnl,
            None,
            None,
            unclassified_posting.flag,
            unclassified_posting.meta
        ))

    new_entry = Transaction(
        entry.meta,
        entry.date,
        entry.flag,
        entry.payee,
        entry.narration,
        entry.tags | frozenset({'power_bohne/de_crypto_private/disposal'}),
        entry.links,
        new_postings
    )
    return new_entry


def de_crypto_private_core(entries, options_map, raw_config=None):
    config, errors = validate_config(entries, options_map, raw_config)
    if errors or config is None:
        return entries, errors

    crypto_assets_accounts = set(config['acc'])
    unclassified = config['unk']

    separate_tx = tx_separator(unclassified, crypto_assets_accounts)

    for i, entry in enumerate(entries):
        accounts = set(get_entry_accounts(entry))
        if not isinstance(entry, Transaction)\
                or unclassified not in accounts\
                or not (crypto_assets_accounts & accounts):
            continue

        st_pnl, lt_pnl, error = separate_tx(entry)
        if error:
            return entries, [error]

        entries[i] = insert_pnls(entry, st_pnl, lt_pnl, config)

    return entries, []


__plugins__ = ['de_crypto_private_core']
