from enum import Enum


class AssetType(Enum):
    CRYPTO = 1
    STABLE = 2
    FIAT = 3


FIAT_TICKERS = {'EUR', 'USD', 'GBP'}
STABLE_TICKERS = {'UST', 'USDT', 'USDC', 'DAI', 'RAI', 'BUSD'}
CRYPTO_TICKERS = {'XMR', 'ETH', 'LTC', 'XRP', 'ETHW', 'LUNA2'}

ASSET_TYPES = {
    **{fiat: AssetType.FIAT for fiat in FIAT_TICKERS},
    **{stable: AssetType.STABLE for stable in STABLE_TICKERS},
    **{crypto: AssetType.CRYPTO for crypto in CRYPTO_TICKERS}
}
