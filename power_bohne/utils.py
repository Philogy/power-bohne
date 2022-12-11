from beancount.core.data import Open, Transaction as _Transaction
from beancount.core.number import D, Decimal


def uncallable_callable(callable_obj):
    def wrapper(*args, **kwargs):
        return callable_obj(*args, **kwargs)
    return wrapper


Transaction = uncallable_callable(_Transaction)


def parse_config_value(value):
    if ',' in value:
        return list(filter(None, value.split(',')))
    return value


def parse_config(config):
    parsed_config = dict()
    for component in config.split():
        key, value = component.split('=', 1)
        parsed_config[key] = parse_config_value(value)
    return parsed_config


def safe_D(inp, assert_error=None) -> Decimal:
    if assert_error is None:
        assert_error = f'{inp} not convertible to decimal'
    from_d = D(inp)
    assert isinstance(from_d, Decimal), assert_error
    return from_d


def get_account_booking_methods(entries):
    accounts = dict()
    for entry in entries:
        if isinstance(entry, Open):
            accounts[entry.account] = entry.booking

    return accounts


class PluginError(Exception):
    def __init__(self, message, filename, lineno=0, entry=None, extended_source=None):
        if extended_source is None:
            extended_source = dict()
        super().__init__(self, message)
        self.source = {'filename': filename, 'lineno': lineno}
        self.message = message
        self.entry = entry
