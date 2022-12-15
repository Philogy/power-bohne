import argparse
from collections import defaultdict
from .metaquery import metaquery
from .gecko import gecko


COMMAND_ALIASES = {
    **metaquery.aliases,
    **gecko.aliases
}

COMMANDS = {
    metaquery.name: metaquery.core_command,
    gecko.name: gecko.core_command
    # 'eth-tx': Command(add_evm_transaction_parser, parse_eth_scan_export)
}


def main():
    parser = argparse.ArgumentParser(description='Business beancount tools')

    all_aliases = defaultdict(list)
    for alias, cmd in COMMAND_ALIASES.items():
        all_aliases[cmd].append(alias)

    subparsers = parser.add_subparsers(dest='command')
    for cmd_name, cmd in COMMANDS.items():
        subparser = subparsers.add_parser(
            cmd_name,
            aliases=all_aliases[cmd_name]
        )
        cmd.parser_add(subparser)

    args = parser.parse_args()
    cmd_alias = args.command

    COMMANDS[COMMAND_ALIASES.get(cmd_alias, cmd_alias)].command_fn(args)


if __name__ == '__main__':
    main()
