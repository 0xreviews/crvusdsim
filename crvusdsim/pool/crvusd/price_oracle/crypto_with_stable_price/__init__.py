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
from curvesim.pool import get_sim_pool
from .base import Oracle
from .weth import OracleWETH
from .wbtc import OracleWBTC
from .sfrxeth import OracleSFRXETH
from .wsteth import OracleWSTETH
from .tbtc import OracleTBTC
from ...conf import LLAMMA_TBTC, LLAMMA_WETH, LLAMMA_SFRXETH, LLAMMA_WBTC, LLAMMA_WSTETH

MAP = {
    LLAMMA_WETH: OracleWETH,
    LLAMMA_WBTC: OracleWBTC,
    LLAMMA_SFRXETH: OracleSFRXETH,
    LLAMMA_WSTETH: OracleWSTETH,
    LLAMMA_TBTC: OracleTBTC,
}


def get_oracle(
    market: str, factory, aggregator, stableswap_all, end_ts: int | None = None
) -> Oracle:
    """Return the appropriate Oracle instance."""
    tricrypto, stableswap = get_pools(market, stableswap_all, end_ts)
    kwargs = make_kwargs(market, aggregator, factory, tricrypto, stableswap)
    return MAP[market.lower()](**kwargs)


def get_tricrypto_addresses(market: str) -> list:
    """Return the TriCrypto pools required for the oracle."""
    if market.lower() in [LLAMMA_WETH, LLAMMA_WBTC, LLAMMA_SFRXETH, LLAMMA_WSTETH]:
        return [
            "0x7f86bf177dd4f3494b841a37e810a34dd56c829b",  # USDC
            "0xf5f5b97624542d72a9e06f04804bf81baa15e2b4",  # USDT
        ]
    elif market.lower() == LLAMMA_TBTC:
        return ["0x2889302a794dA87fBF1D6Db415C1492194663D13"]
    else:
        raise NotImplementedError("Invalid market: %s" % market)


def get_stableswap_addresses(market: str) -> list:
    if market.lower() in [LLAMMA_WETH, LLAMMA_WBTC, LLAMMA_SFRXETH, LLAMMA_WSTETH]:
        return [
            "0x4dece678ceceb27446b35c672dc7d61f30bad69e",  # USDC
            "0x390f3595bca2df7d23783dfd126427cceb997bf4",  # USDT
        ]
    elif market.lower() == LLAMMA_TBTC:
        return []
    else:
        raise NotImplementedError("Invalid market: %s" % market)


def get_pools(market: str, stableswap_all, end_ts: int | None = None) -> tuple:
    """Return the pools required to construct the oracle."""
    tricrypto_addresses = get_tricrypto_addresses(market)
    tricrypto = [
        get_sim_pool(a, balanced=False, end_ts=end_ts) for a in tricrypto_addresses
    ]
    stableswap = []
    stableswap_addresses = get_stableswap_addresses(market)
    for address in stableswap_addresses:
        for spool in stableswap_all:
            if spool.address == address:
                stableswap.append(spool)
                break
    return tricrypto, stableswap


def make_kwargs(market: str, aggregator, factory, tricrypto, stableswap) -> dict:
    kwargs = {
        "tricrypto": tricrypto,
        "stableswap": stableswap,
        "stable_aggregator": aggregator,
        "factory": factory,
        "n_pools": len(tricrypto),
        "tvl_ma_time": 50000,
    }
    if market in [LLAMMA_WETH, LLAMMA_SFRXETH, LLAMMA_WSTETH]:
        kwargs["ix"] = [1, 1]
    elif market == LLAMMA_WBTC:
        kwargs["ix"] = [0, 0]
    elif market == LLAMMA_TBTC:
        kwargs["ix"] = [0]
    else:
        raise NotImplementedError("Invalid market: %s" % market)

    return kwargs
