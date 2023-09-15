from hypothesis import given, settings
from hypothesis import strategies as st

from crvusdsim.pool.crvusd.stable_swap import CurveStableSwapPool
from test.pool.conftest import create_stable_swap

# @given(
#     ns=st.lists(st.integers(min_value=1, max_value=20), min_size=5, max_size=5),
# )
def test_stableswap_add_remove_liquidity(accounts):
    pool = create_stable_swap()
    amounts = [10000 * 10**18] * pool.n

    totalsupply_before = pool.totalSupply
    lp_added = pool.add_liquidity(amounts, accounts[0])

    assert pool.balanceOf[accounts[0]] == lp_added
    assert pool.totalSupply == lp_added + totalsupply_before

    remove_amounts = pool.remove_liquidity(lp_added, [0, 0, 0], accounts[0])
    for i in range(len(remove_amounts)):
        assert remove_amounts[i] == amounts[i]
    
def test_stableswap_lp_transfer(accounts):
    pool = create_stable_swap()
    amounts = [10000 * 10**18] * pool.n
    lp_balance = pool.add_liquidity(amounts, accounts[0])

    pool.transfer(accounts[0], accounts[1], lp_balance)

    assert pool.balanceOf[accounts[0]] == 0
    assert pool.balanceOf[accounts[1]] == lp_balance



