from argparse import ArgumentParser
from .vib_utils import Command, CoreCommand
import beancount.loader
from beancount.core.data import Transaction
from toolz import curry
from collections import defaultdict


def add_billvoice_parser(parser: ArgumentParser):
    parser.add_argument('filepath')
    parser.add_argument('-b', '--bills', action='store_true')
    parser.add_argument('-i', '--invoices', action='store_true')


@curry
def parse_tx(group_name, entry):
    if not isinstance(entry, Transaction):
        return

    g_sep = f'{group_name}/'

    tags = list(filter(lambda t: t.startswith(g_sep), entry.tags))
    links = list(filter(lambda t: t.startswith(g_sep), entry.links))
    if not tags or not links:
        return

    if len(tags) > 1:
        raise ValueError(
            f'Found {len(tags)} links in {entry.date.strftime("%Y-%m-%d")} * {entry.payee} | {entry.narration} for {group_name}'
        )
    if len(links) > 1:
        raise ValueError(
            f'Found {len(links)} links in {entry.date.strftime("%Y-%m-%d")} * {entry.payee} | {entry.narration} for {group_name}'
        )

    return tags[0].replace(g_sep, ''), links[0].replace(g_sep, ''), entry


def process_group(group_name, entries, args):
    is_atomic = dict()
    impacts = defaultdict(dict)
    last_num = -1
    for tag, link, entry in entries:
        assert tag in ('atomic', 'open', 'close'), \
            f'Invalid tag {group_name}/{tag}'
        assert link.isdigit(), \
            f'Invalid group num {group_name}/{link} not valid number'
        num = int(link)
        last_num = max(num, last_num)
        if tag == 'atomic':
            assert num not in is_atomic, f'Duplicate atomic {group_name}/{link}'
            is_atomic[num] = True
            impacts[num]['open'] = entry
            impacts[num]['close'] = entry
        else:
            assert tag not in impacts[num], f'Duplicate <{tag}> for {group_name}/{link}'
            is_atomic[num] = False
            impacts[num][tag] = entry

    width = len(str(last_num))
    print(f'## {group_name.upper()}')
    for num in range(1, last_num + 1):
        if num not in is_atomic:
            status = 'UNUSED 👀'
            date = None
        elif is_atomic[num]:
            status = 'CLOSED ✅'
            date = impacts[num]['open'].date
        else:
            has_open = impacts[num].get('open') is not None
            has_close = impacts[num].get('close') is not None
            assert has_open or has_close, 'weird state'
            if has_close:
                date = impacts[num]['close'].date
                if has_open:
                    status = 'CLOSED ✅'
                else:
                    status = 'CLOSED ONLY ❌'
            else:
                date = impacts[num]['open'].date
                status = 'OPEN   ⚠️ '
        date_str = '' if date is None else f' ({date.strftime("%Y-%m-%d")})'
        print(f'- {str(num).zfill(width)}   {status}{date_str}')


def billvoice_cmd(args):
    entries, errors, _ = beancount.loader.load_file(args.filepath)
    if errors:
        raise errors[0]

    if args.bills:
        process_group(
            'bills',
            list(filter(None, map(parse_tx('bills'), entries))),
            args
        )
    if args.invoices:
        process_group(
            'invoices',
            list(filter(None, map(parse_tx('invoices'), entries))),
            args
        )


billvoice = Command(
    'billvoice',
    ['bv'],
    CoreCommand(add_billvoice_parser, billvoice_cmd)
)
