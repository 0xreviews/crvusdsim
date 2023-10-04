"""
crvUSD Stablecoin
"""

from .conf import STABLECOIN_TOKEN_CONF

from crvusdsim.pool.crvusd.utils.ERC20 import ERC20


class StableCoin(ERC20):
    def __init__(
        self,
        address: str = STABLECOIN_TOKEN_CONF["address"],
        name: str = STABLECOIN_TOKEN_CONF["name"],
        symbol: str = STABLECOIN_TOKEN_CONF["symbol"],
        decimals: int = STABLECOIN_TOKEN_CONF["decimals"],
    ):
        ERC20.__init__(self, address, name, symbol, decimals)
