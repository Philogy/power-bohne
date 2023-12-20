import os
import json
from typing import Any, Optional
from contextlib import contextmanager
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

    def __init__(self, message: str, filename: str, lineno: int = 0, entry: Optional[Any] = None):
        super().__init__(self, message)
        self.message = message
        self.entry = entry
        self.source = {'filename': filename, 'lineno': lineno}

    @classmethod
    @contextmanager
    def capture_assert(
        cls,
        error_out: list['PluginError'],
        entry: Optional[Any] = None,
        filename: Optional[str] = None,
        lineno: Optional[int] = None
    ):
        current_filename: Optional[str] = None
        current_lineno: Optional[int] = None
        if entry is not None:
            current_filename = entry.meta['filename']
            current_lineno = entry.meta['lineno']
        if filename is not None:
            current_filename = filename
        if lineno is not None:
            current_lineno = lineno
        assert isinstance(current_filename, str)
        assert isinstance(current_lineno, int), \
            f'Expected lineno to be int instead got {current_lineno!r} ({type(current_lineno)})'

        try:
            yield
        except AssertionError as e:
            error_out.append(PluginError(
                e.args[0],
                current_filename,
                current_lineno,
                entry
            ))


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
