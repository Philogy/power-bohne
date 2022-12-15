from collections import namedtuple

Command = namedtuple('Command', ['name', 'aliases', 'core_command'])
CoreCommand = namedtuple('CoreCommand', ['parser_add', 'command_fn'])
