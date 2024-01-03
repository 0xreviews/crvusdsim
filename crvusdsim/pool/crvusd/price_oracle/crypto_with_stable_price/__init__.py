"""
Provides all the oracle implementations for
the crypto with stable price oracle.

Each market has its own implementation:
1. WBTC & WETH: use the USDC/WBTC/WETH and USDT/WBTC/WETH TriCrypto-ng
    pools and the USDC/crvUSD and USDT/crvUSD StableSwap pools to 
    generate prices.
2. sfrxETH & wstETH: do the same as (1) but with an additional conversion
    from WETH price to derivative price. We perform this conversion using
    an input `p_staked` parameter provided by the function caller. This
    avoids having to explicitly simulate an additional stableswap pool
    and the staking contract.
3. tBTC: Uses just the crvUSD/tBTC/wstETH TriCrypto-ng pool to provide
    prices.
"""
"""
Provides a factory for creating the right
oracle for a given market.
"""
from .base import Oracle
from .weth import OracleWETH
from .wbtc import OracleWBTC
from .sfrxeth import OracleSFRXETH
from .wsteth import OracleWSTETH
from .tbtc import OracleTBTC

MAP = {
    "weth": OracleWETH,
    "wbtc": OracleWBTC,
    "sfrxeth": OracleSFRXETH,
    "wsteth": OracleWSTETH,
    "tbtc": OracleTBTC,
}


def get_oracle(market: str, *args, **kwargs) -> Oracle:
    """Return the appropriate Oracle instance."""
    return MAP[market](*args, **kwargs)
