"""
crvUSD Stablecoin
"""
from collections import defaultdict

from crvusdsim.pool.crvusd.utils.ERC20 import ERC20

STABLECOIN_TOKEN_CONF = {
    "address": "0xf939e0a03fb07f59a73314e73794be0e57ac1b4e",
    "symbol": "crvUSD",
    "name": "Curve.fi Stablecoin",
    "decimals": 18,
}

class StableCoin(ERC20):

    def __init__(
        self,
        address: str = STABLECOIN_TOKEN_CONF["address"],
        name: str = STABLECOIN_TOKEN_CONF["name"],
        symbol: str = STABLECOIN_TOKEN_CONF["symbol"],
        decimals: int = STABLECOIN_TOKEN_CONF["decimals"],
    ):
        ERC20.__init__(self, address, name, symbol, decimals)
