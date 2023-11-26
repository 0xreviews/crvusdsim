from hypothesis import given, settings
from hypothesis import strategies as st

from ..utils import approx
from ..conftest import STABLE_A,STABLE_N,STABLE_FEE
from crvusdsim.pool.crvusd.stableswap import CurveStableSwapPool


# @given(
#     ns=st.lists(st.integers(min_value=1, max_value=20), min_size=5, max_size=5),
# )
def test_stableswap_add_remove_liquidity(accounts, stableswaps):
    user = accounts[0]
    pool = stableswaps[0]
    amounts = [10000 * 10**18] * pool.n
    for i in range(len(amounts)):
        pool.coins[i]._mint(user, amounts[i])

    totalsupply_before = pool.totalSupply
    lp_added = pool.add_liquidity(amounts, user)

    assert pool.balanceOf[user] == lp_added
    assert pool.totalSupply == lp_added + totalsupply_before

    remove_amounts = pool.remove_liquidity(lp_added, [0, 0, 0], user)
    for i in range(len(remove_amounts)):
        assert approx(remove_amounts[i], amounts[i], 1e-2)


def test_stableswap_lp_transfer(accounts, stableswaps):
    user = accounts[0]
    pool = stableswaps[0]
    amounts = [10000 * 10**18] * pool.n
    for i in range(len(amounts)):
        pool.coins[i]._mint(user, amounts[i])

    lp_balance = pool.add_liquidity(amounts, user)

    pool.transfer(user, accounts[1], lp_balance)

    assert pool.balanceOf[user] == 0
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


def test_stableswap_imbalance(accounts, stablecoin, other_coins):
    peg_coin = other_coins[0]
    pool = CurveStableSwapPool(
        name="crvUSD/%s" % (peg_coin.symbol),
        symbol="crvUSD-%s" % (peg_coin.symbol),
        A=STABLE_A,
        D=[1,1],
        n=STABLE_N,
        fee=STABLE_FEE,
        coins=[peg_coin, stablecoin],
    )

    amounts = [1449474484878008769590815, 3096768931877039410568459]
    for i in range(len(pool.coins)):
        pool.coins[i]._mint(accounts[0], amounts[i])
    
    pool.add_liquidity(amounts, _receiver=accounts[0])

    buy_amount = 3.968282314606846e+19
    dx = pool.get_dx(0, 1, buy_amount)
