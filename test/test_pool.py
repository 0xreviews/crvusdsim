from hypothesis import given
from hypothesis import strategies as st
import pytest
from crvusdsim.pool.crvusd.pool import LLAMMAPool
from crvusdsim.pool.crvusd.price_oracle.price_oracle import PriceOracle
from .conftest import approx

def init_pool(A: int, init_price: int):
    price_oracle = PriceOracle(init_price)
    amm = LLAMMAPool(
        A=A,
        fee=6 * 10**15,
        BASE_PRICE=init_price,
        admin_fee=0,
        price_oracle_contract=price_oracle,
        collateral= {
            "address": "wstETH address",
            "precision": 1,
        },
    )
    return amm, price_oracle


def test_p_oracle_updown():
    
    A = 100
    INIT_PRICE = 2000 * 10**18
    amm, price_oracle = init_pool(A, init_price=INIT_PRICE)
    p_base = amm.get_base_price()

    assert amm.p_oracle_up(0) == p_base
    assert approx(amm.p_oracle_down(0), p_base * (A - 1) // A, 1e-14)

    for i in range(-10, 10):
        mul = ((A - 1) / A) ** i
        p_up = p_base * mul
        p_down = p_up * (A - 1) / A
        assert approx(amm.p_oracle_up(i), p_up, 1e-14)
        assert approx(amm.p_oracle_down(i), p_down, 1e-14)


DEAD_SHARES = 10**3
@given(
    amounts=st.lists(st.integers(min_value=0, max_value=10**6 * 10**18), min_size=5, max_size=5),
    ns=st.lists(st.integers(min_value=-20, max_value=20), min_size=5, max_size=5),
    dns=st.lists(st.integers(min_value=4, max_value=20), min_size=5, max_size=5),
    fracs=st.lists(st.integers(min_value=0, max_value=10**18), min_size=5, max_size=5)
)
def test_deposit_withdraw(amounts, accounts, ns, dns, fracs):
    amm, price_oracle = init_pool(100, init_price=2000 * 10**18)
    deposits = {}
    precisions = {}
    for user, amount, n1, dn in zip(accounts, amounts, ns, dns):
        if amount <= dn:
            precisions[user] = DEAD_SHARES
        else:
            precisions[user] = DEAD_SHARES / (amount // (dn + 1)) + 1e-6
        n2 = n1 + dn
        if amount // (dn + 1) <= 100:
            with pytest.raises(AssertionError, match='Amount too low'):
                amm.deposit_range(user, amount, n1, n2)
        else:
            amm.deposit_range(user, amount, n1, n2)
            deposits[user] = amount

        for user, n1 in zip(accounts, ns):
            if user in deposits:
                if n1 >= 0:
                    y_up = amm.get_y_up(user)
                    assert approx(y_up, deposits[user], precisions[user], 25)
                else:
                    assert amm.get_y_up(user) < deposits[user]  # price manipulation caused loss for user
            else:
                assert amm.get_y_up(user) == 0

        for user, frac, amount in zip(accounts, fracs, amounts):
            if user in deposits:
                before = amm.get_sum_xy(user)
                amm.withdraw(user, frac)
                after = amm.get_sum_xy(user)
                assert approx(before[1] - after[1], deposits[user] * frac / 1e18, precisions[user], 25 + deposits[user] * precisions[user])
            else:
                with pytest.raises(AssertionError, match="No deposits"):
                    amm.withdraw(user, frac)