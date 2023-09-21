import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from crvusdsim.pool.crvusd.LLAMMA import LLAMMAPool
from crvusdsim.pool.crvusd.price_oracle.price_oracle import PriceOracle
from crvusdsim.pool.crvusd.stableswap import ARBITRAGUR
from test.utils import approx
from test.conftest import INIT_PRICE, create_amm, price_oracle


@given(
    amounts=st.lists(st.floats(min_value=0.01, max_value=1e6), min_size=5, max_size=5),
    ns=st.lists(st.integers(min_value=1, max_value=20), min_size=5, max_size=5),
    dns=st.lists(st.integers(min_value=0, max_value=20), min_size=5, max_size=5),
)
def test_dydx_limits(amounts, accounts, ns, dns):
    amm, price_oracle = create_amm()
    amounts = list(map(lambda x: int(x * 10**18), amounts))

    for user, amount, n1, dn in zip(accounts, amounts, ns, dns):
        n2 = n1 + dn
        amm.COLLATERAL_TOKEN._mint(user, amount)
        amm.COLLATERAL_TOKEN.transfer(user, amm.address, amount)
        amm.deposit_range(user, amount, n1, n2)

    # Swap 0
    dx, dy = amm.get_dydx(0, 1, 0)
    assert dx == 0 and dy == 0
    dx, dy = amm.get_dydx(1, 0, 0)
    assert dx == dy == 0

    # Small swap
    dy, dx = amm.get_dydx(0, 1, 10 ** (18 - 6))  # 0.000001 ETH
    assert dy == 10**12
    assert approx(dx, dy * INIT_PRICE / 10**18, 4e-2 + 2 * min(ns) / amm.A)
    dy, dx = amm.get_dydx(1, 0, 10 ** (18 - 4))  # No liquidity
    assert dx == 0
    assert dy == 0  # Rounded down

    # Huge swap
    dy, dx = amm.get_dydx(0, 1, 10**12 * 10**18)
    assert dy < 10**12 * 10**18  # Less than desired amount
    assert abs(dy - sum(amounts)) <= 1000  # but everything is bought
    dy, dx = amm.get_dydx(1, 0, 10**12 * 10**18)
    assert dx == 0
    assert dy == 0  # Rounded down


@given(
    amounts=st.lists(st.floats(min_value=0.01, max_value=1e6), min_size=5, max_size=5),
    ns=st.lists(st.integers(min_value=1, max_value=20), min_size=5, max_size=5),
    dns=st.lists(st.integers(min_value=0, max_value=20), min_size=5, max_size=5),
)
def test_dydx_compare_to_dxdy(amounts, accounts, ns, dns):
    amm, price_oracle = create_amm()
    amounts = list(map(lambda x: int(x * 10**18), amounts))

    for user, amount, n1, dn in zip(accounts, amounts, ns, dns):
        n2 = n1 + dn
        amm.COLLATERAL_TOKEN._mint(user, amount)
        amm.COLLATERAL_TOKEN.transfer(user, amm.address, amount)
        amm.deposit_range(user, amount, n1, n2)

    # Swap 0
    dy, dx = amm.get_dydx(0, 1, 0)
    assert dx == dy == 0
    dy, dx = amm.get_dydx(1, 0, 0)
    assert dx == dy == 0

    # Small swap
    dy1, dx1 = amm.get_dydx(0, 1, 10 ** (18 - 2))
    dx2, dy2 = amm.get_dxdy(0, 1, dx1)
    assert dx1 == dx2
    assert abs(dy1 - dy2) <= 10**(18-4)

    dx1, dy1 = amm.get_dxdy(0, 1, 10 ** (18 - 2))
    dy2, dx2 = amm.get_dydx(0, 1, dy1)
    assert abs(dx1 - dx2) <= 10**(18-4)
    assert dy1 == dy2

    dy, dx = amm.get_dydx(1, 0, 10 ** (18 - 2))  # No liquidity
    assert dx == 0
    assert dy == 0  # Rounded down

    # Huge swap
    dy1, dx1 = amm.get_dydx(0, 1, 10**12 * 10**18)
    dx2, dy2 = amm.get_dxdy(0, 1, dx1)
    assert dy1 < 10**12 * 10**18  # Less than all is desired
    assert abs(dy1 - sum(amounts)) <= 1000  # but everything is bought
    assert dx1 == dx2
    assert dy2 <= dy1  # We might get less because AMM rounds in its favor
    assert abs(dy1 - dy2) <= 1

    dx1, dy1 = amm.get_dxdy(0, 1, 10**12 * 10**18)
    dy2, dx2 = amm.get_dydx(0, 1, dy1)
    assert dx1 < 10**12 * 10**18  # Less than all is spent
    assert abs(dy1 - sum(amounts)) <= 1000  # but everything is bought
    assert dx1 == dx2
    assert dy1 == dy2

    dy, dx = amm.get_dydx(1, 0, 10**12 * 10**18)  # No liquidity
    assert dx == 0
    assert dy == 0  # Rounded down


@given(
    amounts=st.lists(st.floats(min_value=0.01, max_value=1e6), min_size=5, max_size=5),
    ns=st.lists(st.integers(min_value=1, max_value=20), min_size=5, max_size=5),
    dns=st.lists(st.integers(min_value=0, max_value=20), min_size=5, max_size=5),
    amount=st.floats(min_value=0, max_value=10e9),
)
def test_exchange_dy_down_up(amounts, accounts, ns, dns, amount):
    amm, price_oracle = create_amm()
    amounts = list(map(lambda x: int(x * 10**18), amounts))
    amount = amount * 10**18

    for user, amount, n1, dn in zip(accounts, amounts, ns, dns):
        n2 = n1 + dn
        amm.COLLATERAL_TOKEN._mint(user, amount)
        amm.COLLATERAL_TOKEN.transfer(user, amm.address, amount)
        if amount // (dn + 1) <= 100:
            with pytest.raises(AssertionError, match="Amount too low"):
                amm.deposit_range(user, amount, n1, n2)
        else:
            amm.deposit_range(user, amount, n1, n2)

    # crvUSD --> ETH (dx - crvUSD, dy - ETH)
    dy, dx = amm.get_dydx(0, 1, amount)
    assert dy <= amount
    dy2, dx2 = amm.get_dydx(0, 1, dy)
    assert dy == dy2
    assert approx(dx, dx2, 1e-6)
    with pytest.raises(AssertionError, match="Slippage"):
        amm.exchange_dy(0, 1, dy2, dx2 - 1)  # crvUSD --> ETH
    amm.BORROWED_TOKEN._mint(ARBITRAGUR, dx2)
    amm.exchange_dy(0, 1, dy2, dx2)  # crvUSD --> ETH

    # ETH --> crvUSD (dx - ETH, dy - crvUSD)
    expected_in_amount = int(dy2 / 0.98)  # two trades charge 1% twice
    out_amount = dx2

    dy, dx = amm.get_dydx(1, 0, out_amount)
    assert approx(
        dx, expected_in_amount, 2e-2
    )  # Not precise because fee is charged on different directions
    assert out_amount - dy <= 1

    with pytest.raises(AssertionError, match="Slippage"):
        amm.exchange_dy(1, 0, out_amount, dx - 1)  # ETH --> crvUSD
    amm.exchange_dy(1, 0, out_amount, dx)  # ETH --> crvUSD
