import pytest
from math import log
from crvusdsim.pool.crvusd.pool import LLAMMAPool

from crvusdsim.pool.crvusd.price_oracle.price_oracle import PriceOracle

A = 100
INIT_PRICE = 3000 * 10**18

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
        collateral= {
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
        collateral= {
            "address": "wstETH address",
            "precision": 1,
        },
    )
    return amm, price_oracle