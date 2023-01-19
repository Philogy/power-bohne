from enum import Enum
from decimal import Decimal
from eth_abi import decode_abi, decode_single
from collections import namedtuple, defaultdict
import os
import dotenv
import requests
import json
import sys
from toolz import curry
from toolz.curried import get
from eth_utils import (to_int, decode_hex, event_abi_to_log_topic,
                       function_signature_to_4byte_selector, to_checksum_address)
from ens import ENS


WAD = Decimal(10 ** 18)

EventReceipt = namedtuple('EventReceipt', [
    'block_hash',
    'block_number',
    'tx_hash',
    'log_index',
    'address',
    'topics',
    'data',
    'name',
    'args'
])

Event = namedtuple('Event', ['name', 'args'])


class TransferType(Enum):
    ETH = 'ETH'
    ERC20 = '<ERC20>'
    ERC721 = '<ERC721>'
    ERC1155 = '<ERC1155>'


class SpecialAddress(Enum):
    Zero = 'ZERO'
    Fee = 'FEE_RECIPIENT'


def get_json(fp):
    with open(fp, 'r') as f:
        return json.load(f)


TRANSFER_EVENTS_ABI = get_json('./power_bohne/abi/transfers.json')

Transfer = namedtuple(
    'Transfer',
    ['frm', 'to', 'ttype', 'asset_contract', 'sub_id', 'amount']
)

AccountGroup = namedtuple('AccountGroup', ['name'])


def hex_to_int(s: str) -> int:
    return int(s[2:], 16)


def short_addr(addr: str) -> str:
    return f'{addr[:8]}..{addr[-6:]}'


def get_rpc(url, method, *params):
    payload = {'id': 1, 'jsonrpc': '2.0',
               'method': method, 'params': list(params)}
    res = requests.post(
        url,
        json=payload,
        headers={'accept': 'application/json',
                 'content-type': 'application/json'}
    ).json()
    if 'error' in res:
        return False, None
    return True, res


def get_samczsun_trace(tx, chain='ethereum'):
    url = f'https://tx.eth.samczsun.com/api/v1/trace/{chain}/{tx}'
    # print(f'url: {url}')
    return requests.get(url).json()


def get_tx(tx_hash, rpc_url, chain='ethereum'):
    s1, receipt = get_rpc(rpc_url, 'eth_getTransactionReceipt', tx_hash)
    if not s1:
        raise Exception('Get receipt failed')
    s2, tx = get_rpc(rpc_url, 'eth_getTransactionByHash', tx_hash)
    if not s2:
        raise Exception('Get tx failed')
    trace = get_samczsun_trace(tx_hash, chain=chain)
    return {
        **receipt['result'],
        **tx['result'],
        'trace': trace
    }


def ends_to_indent(ends):
    if len(ends) <= 1:
        return ''
    leading_indent = ''.join(
        '│   ' if not end else '    '
        for end in ends[:-1]
    )
    return leading_indent + '├└'[ends[-1]] + '───'


def disp_tx_path(node, depth=0, ends=(True,), tx_parse_event=lambda *_: None):
    indent = ends_to_indent(ends)
    path = node['path']
    t = node['type']
    if t == 'call':
        frm = node['from']
        to = node['to']
        call_type = node['variant']
        if call_type == 'call':
            value = hex_to_int(node['value'])
            value_as_str = f' [{value / 1e18:,.6f} ETH]'
        else:
            value_as_str = ''
        print(
            f'{indent}({path}) {call_type} {short_addr(to_checksum_address(frm))} -> {short_addr(to_checksum_address(to))}{value_as_str}'
        )
    elif t == 'log':
        topics = node['topics']
        event_data = node['data']
        event = tx_parse_event(topics, event_data)
        if event is None or event.name is None or event.args is None:
            print(f'{indent}({path}) {t} (<Unknown>)')
            topic_indent = ends_to_indent(ends + (False,))
            for i, topic in enumerate(topics, start=1):
                print(f'{topic_indent}topic {i}: {topic}')
            data_indent = ends_to_indent(ends + (True,))
            print(f'{data_indent}data: {event_data}')
        else:
            name, args = event
            print(f'{indent}({path}) {t} ({name})')
            largest_arg_name = max(map(len, args.keys()))
            for i, (arg_name, arg_value) in enumerate(args.items(), start=1):
                padding = ' ' * (largest_arg_name - len(arg_name))
                arg_indent = ends_to_indent(ends + (i == len(args),))
                print(f'{arg_indent} {arg_name}:{padding} {arg_value}')
    else:
        print(f'{indent}({path}) {t}')
    children = node.get('children', [])
    for i, child_node in enumerate(children, start=1):
        disp_tx_path(
            child_node,
            depth + 1,
            ends + (i == len(children),),
            tx_parse_event=tx_parse_event
        )


@curry
def parse_event(topic_map, topics, data) -> Event:
    event_id = decode_hex(topics[0]), len(topics)
    event_abi = topic_map.get(event_id)
    if event_abi is None:
        return Event(None, None)

    indexed_args = {}
    data_types = []
    data_arg_names = []
    topic_ind = 1
    for inp in event_abi['inputs']:
        if inp['indexed']:
            indexed_args[inp['name']] = decode_single(
                inp['type'],
                decode_hex(topics[topic_ind])
            )
            topic_ind += 1
        else:
            data_types.append(inp['type'])
            data_arg_names.append(inp['name'])
    decoded_data = decode_abi(data_types, decode_hex(data))

    return Event(event_abi['name'], {
        **indexed_args,
        **dict(zip(data_arg_names, decoded_data))
    })


@curry
def parse_event_receipt(topic_map, event_receipt):
    event_comps = (
        event_receipt['blockHash'],
        hex_to_int(event_receipt['blockNumber']),
        event_receipt['transactionHash'],
        hex_to_int(event_receipt['logIndex']),
        event_receipt['address'],
        event_receipt['topics'],
        event_receipt['data']
    )

    name, args = parse_event(
        topic_map,
        event_receipt['topics'],
        event_receipt['data']
    )
    return EventReceipt(*event_comps, name, args)


def get_topic_count(comp):
    return 1 + sum(map(get('indexed'), comp['inputs']))


def build_topic_map(abi: list[dict]):
    return {
        (event_abi_to_log_topic(comp), get_topic_count(comp)): comp
        for comp in abi
        if comp['type'] == 'event'
    }


def is_nft(rpc_url, addr):
    success, res = get_rpc(
        rpc_url,
        'eth_call',
        {
            'to': addr,
            'data': '0x01ffc9a780ac58cd00000000000000000000000000000000000000000000000000000000'
        },
        'latest'
    )
    return success\
        and len(ret_data := decode_hex(res['result'])) == 32\
        and decode_single('uint', ret_data) == 1


def convert_addr(addr):
    if addr == '0x0000000000000000000000000000000000000000':
        return SpecialAddress.Zero
    return addr


def event_to_transfers(event: Event, addr) -> Transfer:
    from_to = convert_addr(event.args['from']), convert_addr(event.args['to'])
    if event.name == 'Transfer':
        if 'tokenId' in event.args:
            yield Transfer(
                *from_to,
                TransferType.ERC721,
                addr,
                event.args['tokenId'],
                1
            )
        else:
            yield Transfer(
                *from_to,
                TransferType.ERC20,
                addr,
                None,
                event.args['amount']
            )
    elif event.name == 'TransferSingle':
        yield Transfer(
            *from_to,
            TransferType.ERC1155,
            addr,
            event.args['id'],
            event.args['value']
        )
    else:
        for token_id, amount in zip(event.args['ids'], event.args['values']):
            yield Transfer(
                *from_to,
                TransferType.ERC1155,
                addr,
                token_id,
                amount
            )


def get_tx_transfers(tx):
    yield Transfer(
        tx['from'],
        SpecialAddress.Fee,
        TransferType.ETH,
        None,
        None,
        hex_to_int(tx['gasUsed']) * hex_to_int(tx['effectiveGasPrice'])
    )
    yield from get_call_node_transfers(tx['trace']['result']['entrypoint'])


def get_call_node_transfers(node, current_addr=None):
    node_type = node['type']
    if node_type == 'log':
        topic_map = build_topic_map(TRANSFER_EVENTS_ABI)
        # print()
        # for (topic1, topic_count), abi in topic_map.items():
        #     print(f'({topic1.hex()}, {topic_count}): {abi}')
        # print()
        event = parse_event(topic_map, node['topics'], node['data'])
        if not (event.name is None or event.args is None):
            yield from event_to_transfers(event, current_addr)
    elif node_type == 'call':
        if node['variant'] == 'call' and (amount := hex_to_int(node['value'])) != 0:
            yield Transfer(node['from'], node['to'], TransferType.ETH, None, None, amount)
        for child_node in node['children']:
            yield from get_call_node_transfers(child_node, node['to'])


def get_account_transfers(tx):
    account_transfers = defaultdict(list)
    for transfer in get_tx_transfers(tx):
        account_transfers[transfer.frm].append(transfer)
        account_transfers[transfer.to].append(transfer)
    return account_transfers


def sign_to_str(x):
    if x > type(x)(0):
        return '+'
    if x == type(x)(0):
        return ' '
    return ''


def disp_addr(tx, addr, ns):
    if not isinstance(addr, str):
        return addr
    data = tx['trace']['result']['addresses'].get(addr)
    addr = to_checksum_address(addr)
    name = ns.name(addr)
    if name is None:
        full_disp = addr
    else:
        full_disp = f'{name} ({short_addr(addr)})'
    if data is None:
        return full_disp
    label = list(data.values())[-1]['label']
    if not label:
        return full_disp
    if name is None:
        return f'"{label}" ({short_addr(addr)})'
    return f'{name} ("{label}" {short_addr(addr)})'


def summarize_transfers(tx, symbols, w3):
    account_transfers = get_account_transfers(tx)
    for account, transfers in account_transfers.items():
        if isinstance(account, SpecialAddress):
            continue
        print(f'{disp_addr(tx, account, ENS.fromWeb3(w3))}:')
        balance_changes = defaultdict(int)
        fee_payment = None
        for transfer in transfers:
            if transfer.to == SpecialAddress.Fee:
                fee_payment = transfer
            sign = -1 if transfer.frm == account else 1
            asset_id = (
                transfer.asset_contract,
                transfer.ttype,
                transfer.sub_id
            )
            balance_changes[asset_id] += sign * transfer.amount
        for (asset_contract, ttype, sub_id), change in balance_changes.items():
            if change == 0 and fee_payment is None:
                continue
            if ttype == TransferType.ETH:
                print(f'    {sign_to_str(change)}{Decimal(change) / WAD:,} ETH')
                if fee_payment is not None:
                    fee = -Decimal(fee_payment.amount)
                    before_fee = Decimal(change) - fee
                    print(
                        f'        (WITHOUT FEE) {sign_to_str(before_fee)}{before_fee / WAD:,} ETH'
                    )
                    print(
                        f'        (  TX  FEE  ) {fee / WAD:,} ETH'
                    )
            else:
                asset = symbols.get(
                    asset_contract,
                    f'UNKNOWN <{short_addr(to_checksum_address(asset_contract))}>'
                )
                if ttype == TransferType.ERC20:
                    print(
                        f'    {sign_to_str(change)}{Decimal(change) / WAD:,} {asset}'
                    )
                elif ttype == TransferType.ERC1155:
                    print(
                        f'    {sign_to_str(change)}{change:,} {asset} #{sub_id}'
                    )
                else:  # ERC721
                    print(
                        f'    {sign_to_str(change)}{change} x #{sub_id} {asset}'
                    )


def prune_trace_children(node):
    node['children'] = [
        prune_trace_children(child)
        for child in node.get('children', [])
        if child['type'] in ('call', 'log')
    ]
    return node


def get_tokens_from_transfers(transfers):
    return {
        transfer.asset_contract
        for transfer in transfers
        if transfer.ttype in (TransferType.ERC20, TransferType.ERC721)
    }


def get_symbols_from_tx(multicaller, tx):
    tokens = list(get_tokens_from_transfers(get_tx_transfers(tx)))
    symbol_selector = function_signature_to_4byte_selector('symbol()')
    results = multicaller.functions.tryAggregate(False, [
        {
            'target': to_checksum_address(token),
            'callData': symbol_selector
        }
        for token in tokens
    ]).call()
    return {
        token: decode_abi(['string'], ret_data)[0]
        for (success, ret_data), token in zip(results, tokens)
        if success
    }


if __name__ == '__main__':
    import json

    dotenv.load_dotenv()

    rpc = os.environ.get('LLAMA_RPC_URL')

    event_topic_map = build_topic_map(
        get_json('./power_bohne/abi/base-events.json')
    )

    tx_hash = sys.argv[1]

    tx = get_tx(tx_hash, rpc)

    prune_trace_children(tx['trace']['result']['entrypoint'])

    disp_tx_path(
        tx['trace']['result']['entrypoint'],
        tx_parse_event=parse_event(event_topic_map)
    )

    # print(json.dumps(tx, indent=2))

    from web3 import Web3
    provider = Web3.HTTPProvider(rpc)
    w3 = Web3(provider)

    multicaller = w3.eth.contract(
        address='0x5BA1e12693Dc8F9c48aAD8770482f4739bEeD696',
        abi=get_json('./power_bohne/abi/multicall.json')
    )

    symbols = get_symbols_from_tx(multicaller, tx)

    print('\n')

    # b = w3.eth.get_block_number()
    summarize_transfers(tx, symbols, w3)

    # n1 = is_nft(rpc, '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2')
    # n2 = is_nft(rpc, '0xC4638af1e01720C4B5df3Bc8D833db6be85d2211')
    # n3 = is_nft(rpc, '0x6B175474E89094C44Da98b954EedeAC495271d0F')
    # print(f'n1, n2, n3: {n1, n2, n3}')
