import pytest
from math import log
from crvusdsim.pool.crvusd.LLAMMA import LLAMMAPool

from crvusdsim.pool.crvusd.price_oracle.price_oracle import PriceOracle
from crvusdsim.pool.crvusd.stable_swap import CurveStableSwapPool

# LLAMMA
A = 100
INIT_PRICE = 3000 * 10**18
# StableSwap
STABLE_N = 2
STABLE_A = 500  # initially, can go higher later
STABLE_FEE = 1000000  # 0.01%
STABLE_ASSET_TYPE = 0
STABLE_MA_EXP_TIME = 866  # 10 min / ln(2)
STABLE_BALANCES = [10**6 * 10**18] * STABLE_N


def approx(x1: int, x2: int, precision: int, abs_precision=None):
    if precision >= 1:
        return True
    result = False
    if abs_precision is not None:
        result = abs(x2 - x1) <= abs_precision
    else:
        abs_precision = 0
    if x2 == 0:
        return abs(x1) <= abs_precision
    elif x1 == 0:
        return abs(x2) <= abs_precision
    return result or (abs(log(x1 / x2)) <= precision)


@pytest.fixture(scope="module")
def accounts():
    return ["user_address_%d" % i for i in range(5)]


@pytest.fixture
def price_oracle():
    price_oracle = PriceOracle(INIT_PRICE)
    return price_oracle


@pytest.fixture
def amm(price_oracle):
    amm = LLAMMAPool(
        A=A,
        BASE_PRICE=INIT_PRICE,
        fee=10**16,
        admin_fee=0,
        price_oracle_contract=price_oracle,
        collateral={
            "symbol": "wstETH",
            "address": "wstETH address",
            "precision": 1,
        },
    )
    return amm


def create_amm():
    price_oracle = PriceOracle(INIT_PRICE)
    amm = LLAMMAPool(
        A=A,
        BASE_PRICE=INIT_PRICE,
        fee=10**16,
        admin_fee=0,
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
