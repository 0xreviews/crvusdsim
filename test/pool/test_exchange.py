import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from crvusdsim.pool.crvusd.pool import LLAMMAPool
from crvusdsim.pool.crvusd.price_oracle.price_oracle import PriceOracle
from .conftest import INIT_PRICE, approx, A, create_amm, price_oracle


@given(
    amounts=st.lists(
        st.integers(min_value=10**16, max_value=10**6 * 10**18),
        min_size=5,
        max_size=5,
    ),
    ns=st.lists(st.integers(min_value=1, max_value=20), min_size=5, max_size=5),
    dns=st.lists(st.integers(min_value=0, max_value=20), min_size=5, max_size=5),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_dxdy_limits(amounts, accounts, ns, dns):
    amm, price_oracle = create_amm()
    for user, amount, n1, dn in zip(accounts, amounts, ns, dns):
        n2 = n1 + dn
        amm.deposit_range(user, amount, n1, n2)

    # Swap 0
    dx, dy = amm.get_dxdy(0, 1, 0)
    assert dx == 0 and dy == 0
    dx, dy = amm.get_dxdy(1, 0, 0)
    assert dx == dy == 0

    # Small swap
    dx, dy = amm.get_dxdy(0, 1, 10 ** (18 - 4))  # $0.0001
    assert dx == 10 ** (18 - 4)
    assert approx(dy, dx * 10**18 / INIT_PRICE, 4e-2 + 2 * min(ns) / amm.A)
    dx, dy = amm.get_dxdy(1, 0, 10**16)  # No liquidity
    assert dx == 0
    assert dy == 0  # Rounded down

    # Huge swap
    dx, dy = amm.get_dxdy(0, 1, 10**12 * 10**18)
    assert dx < 10**12 * 10**18  # Less than all is spent
    assert abs(dy - sum(amounts)) <= 1000  # but everything is bought
    dx, dy = amm.get_dxdy(1, 0, 10**12 * 10**18)
    assert dx == 0
    assert dy == 0  # Rounded down


@given(
    amounts=st.lists(
        st.integers(min_value=10**16, max_value=10**6 * 10**18),
        min_size=5,
        max_size=5,
    ),
    ns=st.lists(st.integers(min_value=1, max_value=20), min_size=5, max_size=5),
    dns=st.lists(st.integers(min_value=0, max_value=20), min_size=5, max_size=5),
    amount=st.integers(min_value=0, max_value=10**9 * 10**6),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_exchange_down_up(amounts, accounts, ns, dns, amount):
    amm, price_oracle = create_amm()
    for user, amount, n1, dn in zip(accounts, amounts, ns, dns):
        n2 = n1 + dn
        if amount // (dn + 1) <= 100:
            with pytest.raises(AssertionError, match="Amount too low"):
                amm.deposit_range(user, amount, n1, n2)
        else:
            amm.deposit_range(user, amount, n1, n2)

    dx, dy = amm.get_dxdy(0, 1, amount)
    assert dx <= amount
    dx2, dy2 = amm.get_dxdy(0, 1, dx)
    assert dx == dx2
    assert approx(dy, dy2, 10**(18-6))
    amm.exchange(0, 1, dx2, 0)

    in_amount = int(dy2 / 0.98)  # two trades charge 1% twice
    expected_out_amount = dx2

    dx, dy = amm.get_dxdy(1, 0, in_amount)
    assert approx(
        dx, in_amount, 5*10**(18-4)
    )  # Not precise because fee is charged on different directions
    assert abs(dy - expected_out_amount) <= 1

    amm.exchange(1, 0, in_amount, 0)
