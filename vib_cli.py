import argparse
import re
from collections import namedtuple, defaultdict
import beancount.loader
from toolz import curry
from beancount.core.data import Transaction
from beancount.parser import printer


def add_meta_query_parser(parser_meta_query):
    parser_meta_query.add_argument('expression', type=str)
    parser_meta_query.add_argument('-t', '--match-tags', action='store_true')
    parser_meta_query.add_argument('-l', '--match-links', action='store_true')
    parser_meta_query.add_argument('-a', '--show-tags', action='store_true')
    parser_meta_query.add_argument('-i', '--show-links', action='store_true')
    parser_meta_query.add_argument('-d', '--show-date', action='store_true')
    parser_meta_query.add_argument('-p', '--show-payee', action='store_true')
    parser_meta_query.add_argument('-n', '--show-narration',
                                   action='store_true')
    parser_meta_query.add_argument('-e', '--show-entry', action='store_true')


def match_in_set(expr, s):
    return s and any(re.search(expr, el) for el in s)


def get_match(args):
    match_tags = args.match_tags
    match_links = args.match_links
    match_any = not (match_tags or match_links)
    return match_tags or match_any, match_links or match_any


@curry
def keep_entry(args, entry):
    if not isinstance(entry, Transaction):
        return False

    expr = args.expression

    match_tags, match_links = get_match(args)
    return (match_tags and match_in_set(expr, entry.tags))\
        or (match_links and match_in_set(expr, entry.links))


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


def meta_query(args):
    entries, errors, options_map = beancount.loader.load_file(args.filepath)
    if errors:
        raise errors[0]

    match_tags, match_links = get_match(args)
    entries = list(filter(keep_entry(args), entries))

    if match_tags:
        print('Tags:')
        for tag in get_tags(entries, args.expression):
            print(tag)

    if match_links:
        if match_tags:
            print()
        print('Links:')
        for link in get_links(entries, args.expression):
            print(link)

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
            if args.show_tags or args.show_links:
                res_str += '\n'

            print(res_str)


Command = namedtuple('Command', ['parser_add', 'command_fn'])


COMMAND_ALIASES = {
    'mq': 'metaquery'
}

COMMANDS = {
    'metaquery': Command(add_meta_query_parser, meta_query)
}


def main():
    parser = argparse.ArgumentParser(description='Business beancount tools')
    parser.add_argument('filepath')

    all_aliases = defaultdict(list)
    for alias, cmd in COMMAND_ALIASES.items():
        all_aliases[cmd].append(alias)

    subparsers = parser.add_subparsers(dest='command')
    for cmd, aliases in all_aliases.items():
        subparser = subparsers.add_parser(cmd, aliases=aliases)
        COMMANDS[cmd].parser_add(subparser)

    args = parser.parse_args()
    cmd_alias = args.command

    COMMANDS[COMMAND_ALIASES.get(cmd_alias, cmd_alias)].command_fn(args)


if __name__ == '__main__':
    main()
