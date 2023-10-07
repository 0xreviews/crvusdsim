from random import random
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from test.utils import approx
from test.conftest import INIT_PRICE, create_amm


def _valid_band_equation(band_index, y0, pool):
    A = pool.A
    y0 = y0 / 1e18
    p_o = pool.price_oracle() / 1e18
    p_o_up = pool.p_oracle_up(band_index) / 1e18
    x = pool.bands_x[band_index] / 1e18
    y = pool.bands_y[band_index] / 1e18

    f = p_o**2 * A * y0 / p_o_up
    g = p_o_up * (A - 1) * y0 / p_o

    inv = (x + f) * (y + g)
    inv2 = p_o * A**2 * y0**2

    assert approx(inv, inv2, 5e-3)
    return True


@given(
    amount=st.integers(min_value=10**16, max_value=10**6 * 10**18),
    frac=st.floats(min_value=0.1, max_value=0.9),
    ns=st.integers(min_value=1, max_value=20),
    dns=st.integers(min_value=0, max_value=20),
)
def test_exchange_dxdy(accounts, amount, ns, dns, frac):
    user = accounts[0]
    n1 = ns
    N = dns + 1
    n2 = ns + dns
    per_y = amount // N

    amm, price_oracle = create_amm()
    # set fee_rate to zero
    amm.fee = 0

    assert amm.dynamic_fee() == 0

    amm.COLLATERAL_TOKEN._mint(amm.address, amount)
    amm.deposit_range(user, amount, n1, n2)

    p_o = amm.p_oracle_up(1)
    price_oracle.set_price(p_o)
    price_oracle._price_oracle = p_o

    for i in range(n1, n2 + 1):
        _valid_band_equation(i, per_y, amm)

    amount_out = int(amount * frac)
    dx1, dy1 = amm.get_dydx(0, 1, amount_out)
    amm.exchange(0, 1, dx1)

    for i in range(n1, n2 + 1):
        _valid_band_equation(i, per_y, amm)


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
        amm.COLLATERAL_TOKEN._mint(user, amount)
        amm.COLLATERAL_TOKEN.transfer(user, amm.address, amount)
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
        amm.COLLATERAL_TOKEN._mint(user, amount)
        amm.COLLATERAL_TOKEN.transfer(user, amm.address, amount)
        if amount // (dn + 1) <= 100:
            with pytest.raises(AssertionError, match="Amount too low"):
                amm.deposit_range(user, amount, n1, n2)
        else:
            amm.deposit_range(user, amount, n1, n2)

    dx, dy = amm.get_dxdy(0, 1, amount)
    assert dx <= amount
    dx2, dy2 = amm.get_dxdy(0, 1, dx)
    assert dx == dx2
    assert approx(dy, dy2, 10 ** (18 - 6))
    amm.exchange(0, 1, dx2, 0)

    in_amount = int(dy2 / 0.98)  # two trades charge 1% twice
    expected_out_amount = dx2

    dx, dy = amm.get_dxdy(1, 0, in_amount)
    assert approx(
        dx, in_amount, 5 * 10 ** (18 - 4)
    )  # Not precise because fee is charged on different directions
    assert abs(dy - expected_out_amount) <= 1

    amm.exchange(1, 0, in_amount, 0)
