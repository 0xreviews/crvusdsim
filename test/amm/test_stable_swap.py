from hypothesis import given, settings
from hypothesis import strategies as st

from ..utils import approx


# @given(
#     ns=st.lists(st.integers(min_value=1, max_value=20), min_size=5, max_size=5),
# )
def test_stableswap_add_remove_liquidity(accounts, stableswaps):
    pool = stableswaps[0]
    amounts = [10000 * 10**18] * pool.n

    totalsupply_before = pool.totalSupply
    lp_added = pool.add_liquidity(amounts, accounts[0])

    assert pool.balanceOf[accounts[0]] == lp_added
    assert pool.totalSupply == lp_added + totalsupply_before

    remove_amounts = pool.remove_liquidity(lp_added, [0, 0, 0], accounts[0])
    for i in range(len(remove_amounts)):
        assert approx(remove_amounts[i], amounts[i], 1e-2)


def test_stableswap_lp_transfer(accounts, stableswaps):
    pool = stableswaps[0]
    amounts = [10000 * 10**18] * pool.n
    lp_balance = pool.add_liquidity(amounts, accounts[0])

    pool.transfer(accounts[0], accounts[1], lp_balance)

    assert pool.balanceOf[accounts[0]] == 0
    assert pool.balanceOf[accounts[1]] == lp_balance


def test_stableswap_get_D(accounts, stableswaps):
    pool = stableswaps[0]
    before_D = pool.get_D_mem(pool.rates, pool.balances, pool.A)

    add_amount = 1000 * 10**18
    pool.add_liquidity([add_amount] * 2)
    assert approx(
        pool.get_D_mem(pool.rates, pool.balances, pool.A),
        before_D + before_D * add_amount // pool.balances[0],
        1e-2,
    )


def test_stableswap_get_p(accounts, stableswaps):
    pool = stableswaps[0]
    before_p = pool.get_p()
    assert before_p == 10**18

    pool.exchange(0, 1, 10000 * 10**18)
    assert before_p < pool.get_p()

    pool.exchange(1, 0, 15000 * 10**18)
    assert before_p > pool.get_p()
