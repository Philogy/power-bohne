import sys
import os
import dotenv
import requests
from collections import defaultdict
from decimal import Decimal as D

dotenv.load_dotenv()

# Instructions:
# Create `.env` file with `ALCHEMY_KEY` property set to your alchemy key
# Run by exeuction `python llama-lend-get-history.py <pool address>`


JSON_HEADER = {
    'accept': 'application/json',
    'content-type': 'application/json'
}


def get_alchmey_asset_transfers(key, **params):
    return requests.post(
        f'https://eth-mainnet.g.alchemy.com/v2/{key}',
        headers=JSON_HEADER,
        json={
            'id': 1,
            'jsonrpc': '2.0',
            'method': 'alchemy_getAssetTransfers',
            'params': [
                {
                    **params
                }
            ]
        }
    ).json()


def hex_to_int(h):
    return int(h[2:], 16)


def get_asset_transfers(pool):
    alchemy_key = os.environ.get('ALCHEMY_KEY')
    transfers_out = get_alchmey_asset_transfers(
        alchemy_key,
        category=['external', 'internal', 'erc721'],
        fromAddress=pool
    )
    transfers_in = get_alchmey_asset_transfers(
        alchemy_key,
        category=['external', 'internal', 'erc721'],
        toAddress=pool
    )

    cleaned_transfers = [
        {
            'from': transfer['from'],
            'to': transfer['to'],
            'hash': transfer['hash'],
            'asset': (transfer['asset'], transfer['rawContract']['address']),
            'denom': hex_to_int(transfer['erc721TokenId'])
            if transfer['value'] is None
            else hex_to_int(transfer['rawContract']['value']),
            'blockNum': hex_to_int(transfer['blockNum'])
        }
        for transfer in
        transfers_out['result']['transfers'] +
        transfers_in['result']['transfers']
    ]

    grouped_transfers = defaultdict(list)
    for transfer in cleaned_transfers:
        grouped_transfers[transfer['hash']].append(transfer)

    sorted_transfers = sorted(
        grouped_transfers.items(),

        key=lambda p: p[1][0]['blockNum']
    )

    return sorted_transfers


def is_eth(asset):
    return asset[0] == 'ETH' and asset[1] is None


def sign(x):
    zero = D(0) if isinstance(x, D) else 0
    if x > zero:
        return '+'
    return ''


def etherscan(tx_hash):
    return f'https://etherscan.io/tx/{tx_hash}'


def format_bean_repay(tx_hash, borrow_txs, interest):
    if len(borrow_txs) == 1:
        borrow_tx, = borrow_txs
        borrow_formatted = f'''  borrow_tx: "{borrow_tx}"
  borrow_tx-link: "{etherscan(borrow_tx)}"
'''
    else:
        borrow_formatted = ''
        for i, borrow_tx in enumerate(borrow_txs, start=1):
            borrow_formatted += f'''  borrow_tx-{i}: "{borrow_tx}"
  borrow_tx-{i}-link: "{etherscan(borrow_tx)}"
'''

    return f'''2023-MM-DD * "Llama Lend" "Gobbler loan repayment + interest" #eth
  txref: "{tx_hash}"
  txref-link: "{etherscan(tx_hash)}"
{borrow_formatted}  Income:Crypto:Lending
  Assets:Crypto:Tokens      {D(interest) / D(10**18)} ETH {{}}
'''


def main():
    pool, *args = sys.argv[1:]
    txs = get_asset_transfers(pool)
    pool = pool.lower()

    beancount = args and args[0] == '-b'
    beancounts = []

    borrows = {}

    for tx_hash, tx_transfers in txs:
        prints = [
            None,
            f'    tx hash: {tx_hash}',
            f'    link: {etherscan(tx_hash)}'
        ]
        tx_type = None
        if len(tx_transfers) == 1 and is_eth((transfer := tx_transfers[0])['asset']):
            if transfer['from'] == pool:
                tx_type = 'WITHDRAWAL'
            elif transfer['to'] == pool:
                tx_type = 'DEPOSIT'
            else:
                raise ValueError(f'Unrecognized: {transfer}')
            amount = transfer['denom']
            prints.append(f'    amount: {amount / 1e18 :,.6f} ETH')
        elif len(tx_transfers) >= 2:
            pool_eth_gain = 0
            tokens_out = []
            tokens_in = []
            for transfer in tx_transfers:
                if transfer['to'] == pool:
                    if is_eth(transfer['asset']):
                        pool_eth_gain += transfer['denom']
                    else:
                        tokens_in.append(transfer['denom'])
                elif transfer['from'] == pool:
                    if is_eth(transfer['asset']):
                        pool_eth_gain -= transfer['denom']
                    else:
                        tokens_out.append(transfer['denom'])
                else:
                    raise ValueError(f'Unrecognized: {transfer}')
            prints.append(
                f'    change: {sign(pool_eth_gain)}{pool_eth_gain/ 1e18:,.6f} ETH'
            )
            if pool_eth_gain > 0 and not tokens_in:
                print(f'tokens_out: {tokens_out}')
                tx_type = 'REPAY'
                total_principal = 0
                borrow_txs = set()
                for token_id in tokens_out:
                    borrow_tx, amount = borrows[token_id]
                    borrow_txs.add(borrow_tx)
                    total_principal += amount
                    del borrows[token_id]
                interest = pool_eth_gain - total_principal
                prints.append(
                    f'    Interest earned: +{D(interest)/ D(10**18)} ETH'
                )
                if borrow_txs:
                    prints.append(f'    Borrow txs:')
                    for borrow_tx in borrow_txs:
                        prints.append(f'     - {etherscan(borrow_tx)}')
                if beancount:
                    beancounts.append(
                        format_bean_repay(tx_hash, borrow_txs, interest)
                    )

            elif pool_eth_gain < 0 and not tokens_out:
                tx_type = 'BORROW'
                for token_id in tokens_in:
                    borrows[token_id] = (
                        tx_hash, -pool_eth_gain // len(tokens_in))
            else:
                raise ValueError(f'Unrecognized: {tx_transfers}')
        elif all(not is_eth(transfer['asset']) for transfer in tx_transfers):
            tx_type = 'LIQUIDATION'
            lost_principal = 0
            assumed_tokens = []
            for transfer in tx_transfers:
                token_id = transfer['denom']
                asset_name, _ = transfer['asset']
                borrow_tx, amount = borrows[token_id]
                lost_principal += amount
                assumed_tokens.append((f'{asset_name}#{token_id}', borrow_tx))
                del borrows[token_id]
            prints.append(
                f'    Forfeited principal: {D(lost_principal) / D(10**18)} ETH')
            prints.append(f'    Assumed tokens:')
            for token, borrow_tx in assumed_tokens:
                prints.append(
                    f'     - {token} (tx: {etherscan(borrow_tx)})'
                )

        else:
            raise ValueError(f'Unrecognized: {tx_transfers}')
        prints[0] = f'tx: {tx_hash[:8]}..{tx_hash[-6:]} [{tx_type}]'

        for p in prints:
            print(p)

        print()

    if beancount:
        print('\n\n' + '-' * 50)

        for b in beancounts:
            print(b)

    print(f'borrows: {borrows}')


if __name__ == '__main__':
    main()
