import pytest
from hypothesis import given
from hypothesis import strategies as st
from ..utils import approx
from ..conftest import INIT_PRICE, create_controller_amm

INIT_PRICE_E1 = INIT_PRICE // 10**18

def test_create_loan(accounts):
    controller, market_amm = create_controller_amm()
    stablecoin = controller.STABLECOIN
    collateral = controller.COLLATERAL_TOKEN
    user = accounts[0]

    initial_amount = 10**25
    c_amount = int(2 * 1e6 * 1e18 * 1.5 / INIT_PRICE_E1)
    l_amount = 2 * 10**6 * 10**18

    with pytest.raises(AssertionError):
        controller.create_loan(user, c_amount, c_amount * INIT_PRICE_E1, 5)

    l_amount = 5 * 10**5 * 10**18
    with pytest.raises(AssertionError, match='Need more ticks'):
        controller.create_loan(user, c_amount, l_amount, 3)
    with pytest.raises(AssertionError, match='Need less ticks'):
        controller.create_loan(user, c_amount, l_amount, 400)

    with pytest.raises(AssertionError, match="Debt too high"):
        controller.create_loan(user, c_amount // 100, l_amount, 5)

    # Phew, the loan finally was created
    old_balance_user = stablecoin.balanceOf[user]
    old_balance_controller = stablecoin.balanceOf[controller.address]
    collateral._mint(user, c_amount)
    controller.create_loan(user, c_amount, l_amount, 5)
    # But cannot do it again
    with pytest.raises(AssertionError, match='Loan already created'):
        controller.create_loan(user, c_amount, 1, 5)

    assert stablecoin.balanceOf[user] - old_balance_user == l_amount
    assert l_amount == old_balance_controller - stablecoin.balanceOf[controller.address]
    # assert collateral_token.balanceOf(user) == initial_amount - c_amount

    assert controller.total_debt() == l_amount
    assert controller.debt(user) == l_amount

    p_up, p_down = controller.user_prices(user)
    p_lim = l_amount / c_amount / (1 - controller.loan_discount/1e18)
    assert approx(p_lim, (p_down * p_up)**0.5 / 1e18, 2 / market_amm.A)

    h = controller.health(user) / 1e18 + 0.02
    assert h >= 0.05 and h <= 0.06

    h = controller.health(user, True) / 1e18 + 0.02
    assert approx(h, c_amount * 3000 / l_amount - 1, 0.02)


def create_existing_loan(accounts):
    controller, market_amm = create_controller_amm()
    stablecoin = controller.STABLECOIN
    collateral = controller.COLLATERAL_TOKEN
    user = accounts[0]
    c_amount = int(2 * 1e6 * 1e18 * 1.5 / INIT_PRICE_E1)
    l_amount = 5 * 10**5 * 10**18
    n = 5

    collateral._mint(user, c_amount)
    controller.create_loan(user, c_amount, l_amount, n)
    return controller, market_amm


def test_repay_all(accounts):
    controller, market_amm = create_existing_loan(accounts)
    stablecoin = controller.STABLECOIN
    user = accounts[0]

    c_amount = int(2 * 1e6 * 1e18 * 1.5 / INIT_PRICE_E1)
    amm = controller.AMM
    controller.repay(2**100, user)
    assert controller.debt(user) == 0
    assert stablecoin.balanceOf[user] == 0
    # assert collateral_token.balanceOf[user] == c_amount
    assert stablecoin.balanceOf[amm.address] == 0
    # assert collateral_token.balanceOf[amm] == 0
    assert controller.total_debt() == 0


def test_repay_half(accounts):
    controller, market_amm = create_existing_loan(accounts)
    stablecoin = controller.STABLECOIN
    user = accounts[0]

    c_amount = int(2 * 1e6 * 1e18 * 1.5 / INIT_PRICE_E1)
    debt = controller.debt(user)
    to_repay = debt // 2

    n_before_0, n_before_1 = market_amm.read_user_tick_numbers(user)
    controller.repay(to_repay, user)
    n_after_0, n_after_1 = market_amm.read_user_tick_numbers(user)

    assert n_before_1 - n_before_0 + 1 == 5
    assert n_after_1 - n_after_0 + 1 == 5
    assert n_after_0 > n_before_0

    assert controller.debt(user) == debt - to_repay
    assert stablecoin.balanceOf[user] == debt - to_repay
    # assert collateral_token.balanceOf[user] == 0
    assert stablecoin.balanceOf[market_amm.address] == 0
    # assert collateral_token.balanceOf[market_amm] == c_amount
    assert controller.total_debt() == debt - to_repay


def test_add_collateral(accounts):
    controller, market_amm = create_existing_loan(accounts)
    stablecoin = controller.STABLECOIN
    collateral = controller.COLLATERAL_TOKEN
    user = accounts[0]

    c_amount = int(2 * 1e6 * 1e18 * 1.5 / 3000)
    debt = controller.debt(user)

    n_before_0, n_before_1 = market_amm.read_user_tick_numbers(user)
    collateral._mint(user, c_amount)
    controller.add_collateral(c_amount, user)
    n_after_0, n_after_1 = market_amm.read_user_tick_numbers(user)

    assert n_before_1 - n_before_0 + 1 == 5
    assert n_after_1 - n_after_0 + 1 == 5
    assert n_after_0 > n_before_0

    assert controller.debt(user) == debt
    assert stablecoin.balanceOf[user] == debt
    # assert collateral_token.balanceOf[user] == 0
    assert stablecoin.balanceOf[market_amm] == 0
    # assert collateral_token.balanceOf[market_amm] == 2 * c_amount
    assert controller.total_debt() == debt


def test_borrow_more(accounts):
    controller, market_amm = create_existing_loan(accounts)
    stablecoin = controller.STABLECOIN
    user = accounts[0]

    debt = controller.debt(user)
    more_debt = debt // 10
    c_amount = int(2 * 1e6 * 1e18 * 1.5 / 3000)

    n_before_0, n_before_1 = market_amm.read_user_tick_numbers(user)
    controller.borrow_more(user, 0, more_debt)
    n_after_0, n_after_1 = market_amm.read_user_tick_numbers(user)

    assert n_before_1 - n_before_0 + 1 == 5
    assert n_after_1 - n_after_0 + 1 == 5
    assert n_after_0 < n_before_0

    assert controller.debt(user) == debt + more_debt
    assert stablecoin.balanceOf[user] == debt + more_debt
    # assert collateral_token.balanceOf[user] == 0
    assert stablecoin.balanceOf[market_amm] == 0
    # assert collateral_token.balanceOf[market_amm] == c_amount
    assert controller.total_debt() == debt + more_debt
