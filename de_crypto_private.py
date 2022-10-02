from .utils import parse_config, get_account_booking_methods, PluginError
from beancount.core.data import Booking
from beancount.core import realization


def validate_config(entries, options_map, raw_config):
    if raw_config is None:
        return None, [PluginError('InvalidConfig: Config empty', options_map['filename'])]

    try:
        config = parse_config(raw_config)
    except:
        return None, [PluginError('InvalidConfig: Faile to parse config, expected: "< key1 >= <value1 > <key2 >= <value2 > < list_key >= <item1_1 > , < item1_2 > , "', filename=options_map['filename'])]

    for required_key in 'st', 'lt', 'acc':
        if required_key not in config:
            return None, [PluginError(f'InvalidConfig: Missing key \'{required_key}\' required', options_map['filename'])]

    if not isinstance(config['acc'], list):
        return None, [PluginError(f'InvalidConfig: \'acc\' must be list, use trailling comma if single item', options_map['filename'])]

    accounts_booking = get_account_booking_methods(entries)
    for account in config['st'], config['lt'], *config['acc']:
        if account not in accounts_booking:
            return None, [PluginError(f'NonexistentAccount: account \'{account}\' not found', filename=options_map['filename'])]

    for asset_account in config['acc']:
        if (method := accounts_booking[asset_account]) != Booking.FIFO:
            return None, [PluginError(f'InvalidBookingMethod: \'{asset_account}\' using "{method}" instead of FIFO', filename=options_map['filename'])]

    return config, []


def de_crypto_private_core(entries, options_map, raw_config=None):
    config, errors = validate_config(entries, options_map, raw_config)
    if errors:
        return entries, errors

    postings = realization.postings_by_account(entries)

    return entries, []


__plugins__ = ['de_crypto_private_core']
