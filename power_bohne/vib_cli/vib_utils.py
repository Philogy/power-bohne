import re
from collections import namedtuple
from typing import NamedTuple

import pytz
from datetime import datetime
from dateutil import parser as dateutil_parser

CoreCommand = namedtuple('CoreCommand', ['parser_add', 'command_fn'])
Command = NamedTuple(
    'Command',
    [
        ('name', str),
        ('aliases', list[str]),
        ('core_command', CoreCommand)
    ]
)


def parse_time(raw_time: str) -> datetime:
    try:
        time = datetime.strptime(raw_time, '%b-%d-%Y %I:%M:%S %p +%Z')
        tz_code = raw_time.split(' ')[-1][1:]
        time_tzaware = time.replace(tzinfo=pytz.timezone(tz_code))
        return datetime.fromtimestamp(time_tzaware.timestamp())
    except:
        pass
    try:
        return dateutil_parser.parse(raw_time)
    except dateutil_parser.ParserError:
        pass
    try:
        return datetime.fromtimestamp(float(raw_time))
    except:
        raise ValueError(f'Could not parse {raw_time!r} as date')
