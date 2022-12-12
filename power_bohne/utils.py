import os
import json
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


class FileCache:
    CACHE_FOLDER = '.power_bohne_cache'

    def __init__(self, fp):
        self.fp = fp
        self.mem_cache = dict()
        self.load()

    def load(self):
        full_path = os.path.join(self.CACHE_FOLDER, self.fp)
        self.mem_cache = dict()
        if not os.path.exists(full_path):
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
        else:
            with open(full_path, 'r') as f:
                try:
                    cache_items = json.load(f)
                    self.mem_cache = dict([
                        (tuple(key) if isinstance(key, list) else key, value)
                        for key, value in cache_items
                    ])
                except json.decoder.JSONDecodeError:
                    with open(full_path, 'w') as fw:
                        fw.write('')  # wipe cache
        return self.mem_cache

    def get(self, key):
        return self.mem_cache.get(key)

    def __getitem__(self, key):
        return self.mem_cache.get(key)

    def __setitem__(self, key, value):
        self.mem_cache[key] = value

    def save(self):
        with open(os.path.join(self.CACHE_FOLDER, self.fp), 'w') as f:
            json.dump(list(self.mem_cache.items()), f)
