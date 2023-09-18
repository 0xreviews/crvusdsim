import pytest

from crvusdsim.pool.crvusd.LLAMMA import LLAMMAPool
from crvusdsim.pool.crvusd.price_oracle.price_oracle import PriceOracle
from crvusdsim.pool.crvusd.stableswap import CurveStableSwapPool

INIT_PRICE = 3000 * 10**18

# LLAMMA
LLAMMA_A = 100
LLAMMA_FEE = 10**16
LLAMMA_ADMIN_FEE = 0

# StableSwap
STABLE_N = 2
STABLE_A = 500  # initially, can go higher later
STABLE_FEE = 1000000  # 0.01%
STABLE_ASSET_TYPE = 0
STABLE_MA_EXP_TIME = 866  # 10 min / ln(2)
STABLE_BALANCES = [10**6 * 10**18] * STABLE_N

@pytest.fixture
def amm(price_oracle, collateral):
    amm = LLAMMAPool(
        A=LLAMMA_A,
        BASE_PRICE=INIT_PRICE,
        fee=LLAMMA_FEE,
        admin_fee=LLAMMA_ADMIN_FEE,
        price_oracle_contract=price_oracle,
        collateral=collateral,
    )
    return amm


def create_amm():
    price_oracle = PriceOracle(INIT_PRICE)
    amm = LLAMMAPool(
        A=LLAMMA_A,
        BASE_PRICE=INIT_PRICE,
        fee=LLAMMA_FEE,
        admin_fee=LLAMMA_ADMIN_FEE,
        price_oracle_contract=price_oracle,
        collateral={
            "symbol": "wstETH",
            "address": "wstETH address",
            "precision": 1,
        },
    )
    return amm, price_oracle


@pytest.fixture
def stable_swap():
    pool = CurveStableSwapPool(
        A=STABLE_A,
        D=STABLE_BALANCES,
        n=STABLE_N,
        fee=STABLE_FEE,
    )
    return pool


def create_stable_swap():
    pool = CurveStableSwapPool(
        A=STABLE_A,
        D=STABLE_BALANCES,
        n=STABLE_N,
        fee=STABLE_FEE,
    )
    return pool