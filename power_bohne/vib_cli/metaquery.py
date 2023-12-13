import re
from argparse import ArgumentParser
from typing import Generator
import beancount.loader
from beancount.parser import printer
from beancount.core.data import Transaction
from toolz import curry
from .vib_utils import Command, CoreCommand


def match_in_set(expr, s):
    return s and any(re.search(expr, el) for el in s)


def get_match(args) -> tuple[bool, ...]:
    match_tags: bool = args.match_tags
    match_links: bool = args.match_links
    match_meta: bool = args.match_metadata
    matching = (match_tags, match_links, match_meta)
    match_any = not any(matching)
    return tuple(map(lambda m: m or match_any, matching))


def get_valid_meta_fields(expr: str, meta: dict[str, str]) -> list[tuple[str, str]]:
    assert ':' in expr, f'Expression does not match <field regex>:<regex>'
    field_expr, val_expr = expr.split(':', 1)
    return [
        (field, value)
        for field, value in meta.items()
        if isinstance(value, str)
        and re.search(field_expr, field)
        and re.search(val_expr, value)
    ]


def matches_meta(expr: str, meta: dict[str, str]) -> bool:
    return bool(get_valid_meta_fields(expr, meta))


@curry
def keep_entry(args, entry):
    if not isinstance(entry, Transaction):
        return False

    expr = args.expression

    match_tags, match_links, match_meta = get_match(args)
    return (match_tags and match_in_set(expr, entry.tags))\
        or (match_links and match_in_set(expr, entry.links))\
        or (match_meta and matches_meta(expr, entry.meta))


def get_tags(entries, expr):
    for entry in entries:
        for tag in entry.tags:
            if re.search(expr, tag):
                yield tag


def get_links(entries, expr):
    for i, entry in enumerate(entries, start=1):
        for link in entry.links:
            if re.search(expr, link):
                yield f'{link} ({i})'


def get_metas(entries, expr: str) -> Generator[str, None, None]:
    field_expr, val_expr = expr.split(':', 1)
    for entry in entries:
        for field, value in entry.meta.items():
            if re.search(field_expr, field) and re.search(val_expr, value):
                yield value


def meta_query(args):
    entries, errors, _ = beancount.loader.load_file(args.filepath)
    if errors:
        raise errors[0]

    match_tags, match_links, match_meta = get_match(args)
    entries = list(filter(keep_entry(args), entries))

    prev = False

    if match_tags:
        if prev:
            print()
        print('Tags:')
        for tag in get_tags(entries, args.expression):
            print(tag)
        prev = True

    if match_links:
        if prev:
            print()
        print('Links:')
        for link in get_links(entries, args.expression):
            print(link)
        prev = True

    if match_meta:
        if prev:
            print()
        print('Metadata:')
        for meta in get_metas(entries, args.expression):
            print(meta)
        prev = True

    # show added info
    print('\nEntries:')
    for entry in entries:
        if args.show_entry:
            printer.print_entry(entry)
        else:
            res_str = ''
            if args.show_date:
                res_str += entry.date.strftime('%Y-%m-%d')
            if args.show_payee:
                res_str += f' "{entry.payee}"'
            if args.show_narration:
                res_str += f' "{entry.narration}"'
            if args.show_tags:
                res_str += ' ' + ' '.join(map(lambda t: f'#{t}', entry.tags))
            if args.show_links:
                res_str += ' ' + ' '.join(map(lambda t: f'^{t}', entry.links))
            if args.show_meta_value:
                fields = get_valid_meta_fields(args.expression, entry.meta)
                if len(fields) == 1:
                    field, value = fields[0]
                    res_str += f' {field}: {value}'
                elif len(fields) > 1:
                    for field, value in fields:
                        res_str += f'\n    {field}: {value}'

            # if args.show_tags or args.show_links:
            #     res_str += '\n'

            if res_str:
                print(res_str)


def add_meta_query_parser(parser: ArgumentParser):
    parser.add_argument('filepath')
    parser.add_argument('expression', type=str)
    parser.add_argument('-m', '--match-metadata', action='store_true')
    parser.add_argument('-t', '--match-tags', action='store_true')
    parser.add_argument('-l', '--match-links', action='store_true')
    parser.add_argument('-a', '--show-tags', action='store_true')
    parser.add_argument('-i', '--show-links', action='store_true')
    parser.add_argument('-d', '--show-date', action='store_true')
    parser.add_argument('-p', '--show-payee', action='store_true')
    parser.add_argument('-n', '--show-narration', action='store_true')
    parser.add_argument('-v', '--show-meta-value', action='store_true')
    parser.add_argument('-e', '--show-entry', action='store_true')


metaquery = Command(
    'metaquery',
    ['mq'],
    CoreCommand(add_meta_query_parser, meta_query)
)
