import argparse
import re
from collections import namedtuple, defaultdict
import beancount.loader
from beancount.data import Transaction


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


def meta_query(args):
    entries, errors, options_map = beancount.loader.load_file(args.filepath)
    if errors:
        raise errors[0]

    for entry in entries:
        if not isinstance(entry, Transaction):
            continue


Command = namedtuple('Command', ['parser_add', 'command_fn'])


COMMAND_ALIASES = {
    'mq': 'metaquery'
}

COMMANDS = {
    'metaquery': Command(add_meta_query_parser, None)
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
