from hypothesis import given, settings
from hypothesis import strategies as st
from crvusdsim.pool.crvusd.LLAMMA import LLAMMAPool
from crvusdsim.pool.crvusd.price_oracle.price_oracle import PriceOracle
from test.conftest import (
    LLAMMA_A,
    LLAMMA_ADMIN_FEE,
    LLAMMA_FEE,
    MARKET_LOAN_DISCOUNT,
    MARKET_LIQUIDATION_DISCOUNT,
    MARKET_DEBT_CEILING,
)


def test_set_debt_ceiling(stablecoin, factory):
    assert factory.STABLECOIN.address == stablecoin.address
    target_address = "0xtarget_address"
    target_ceiling = 10**24
    factory.set_debt_ceiling(_to=target_address, debt_ceiling=target_ceiling)
    assert factory.debt_ceiling[target_address] == target_ceiling, "debt ceiling wrong"


def test_add_market(stablecoin, collateral, price_oracle, monetary_policy, factory):
    controller, pool = factory.add_market(
        token=collateral,
        A=LLAMMA_A,
        fee=LLAMMA_FEE,
        admin_fee=LLAMMA_ADMIN_FEE,
        _price_oracle_contract=price_oracle,
        monetary_policy=monetary_policy,
        loan_discount=MARKET_LOAN_DISCOUNT,
        liquidation_discount=MARKET_LIQUIDATION_DISCOUNT,
        debt_ceiling=MARKET_DEBT_CEILING,
    )

    N = factory.n_collaterals
    assert N == 1
    assert factory.collaterals[N - 1] == collateral.address
    assert factory.collaterals_index[collateral.address][0] == 2**128 + N - 1
    assert factory.amms[N - 1] == pool
    assert factory.controllers[N - 1] == controller
    assert factory.debt_ceiling[controller.address] == MARKET_DEBT_CEILING
    assert factory.debt_ceiling_residual[controller.address] == MARKET_DEBT_CEILING
    assert stablecoin.balanceOf[controller.address] == MARKET_DEBT_CEILING
    assert pool.BORROWED_TOKEN == stablecoin
    assert controller.STABLECOIN == stablecoin
