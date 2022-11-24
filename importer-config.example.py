from power_bohne.importers import KrakenImporter

CONFIG = [
    KrakenImporter(
        'EUR',
        'Assets:Cash:Kraken',
        'Assets:Crypto:Net-Cash-Out',
        'Assets:Foreign-Fiat',
        'Assets:Crypto:Stable',
        'Assets:Crypto:Tokens',
        'Expenses:Crypto:Withdrawal-Fees',
        'Income:Crypto:SL-Unk',
        'Income:Forex-PnL'
    )
]
