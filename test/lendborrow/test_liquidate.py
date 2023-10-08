import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from test.conftest import create_controller_amm, stablecoin
from ..utils import approx


N = 5


@pytest.fixture(scope="module")
def controller_for_liquidation(accounts):
    def f(sleep_time, discount):
        controller, market_amm = create_controller_amm()
        stablecoin = controller.STABLECOIN
        collateral = controller.COLLATERAL_TOKEN
        monetary_policy = controller.monetary_policy
        pegkeepers = monetary_policy.peg_keepers
        price_oracle = market_amm.price_oracle_contract

        user = accounts[0]
        user2 = accounts[2]
        fee_receiver = accounts[0]  # same as liquidator
        collateral_amount = 10**18
        controller.set_amm_fee(10**6)
        monetary_policy.set_rate(int(1e18 * 1.0 / 365 / 86400))  # 100% APY

        debt = controller.max_borrowable(collateral_amount, N)

        collateral._mint(user, collateral_amount)
        controller.create_loan(user, collateral_amount, debt, N)
        health_0 = controller.health(user)
        # We put mostly USD into AMM, and its quantity remains constant while
        # interest is accruing. Therefore, we will be at liquidation at some point
        dx, dy, fees = market_amm.exchange(0, 1, debt, 0, _receiver=user)
        health_1 = controller.health(user)

        assert approx(health_0, health_1, 1e-6)

        # boa.env.time_travel(sleep_time)
        price_oracle._increment_timestamp(timedelta=sleep_time)
        market_amm._increment_timestamp(timedelta=sleep_time)
        for pk in pegkeepers:
            pk._increment_timestamp(timedelta=sleep_time)

        health_2 = controller.health(user)
        # Still healthy but liquidation threshold satisfied
        assert health_2 < 0
        if discount > 0:
            assert health_2 + discount > 0

        # Stop charging fees to have enough coins to liquidate in existence a block before
        monetary_policy.set_rate(0)

        controller.collect_fees()
        # Check that we earned the same in admin fees as we need to liquidate
        # Calculation is not precise because of dead shares, but the last withdrawal will put dust in admin fees
        # @todo assert approx(stablecoin.balanceOf[fee_receiver], controller.tokens_to_liquidate(user), 1e-10)

        # Borrow some more funds to repay for our overchargings with DEAD_SHARES
        collateral._mint(user2, collateral_amount)
        controller.create_loan(user2, collateral_amount, debt, N)

        return controller, market_amm, stablecoin

    return f


def test_liquidate(accounts, controller_for_liquidation):
    controller, market_amm, stablecoin = controller_for_liquidation(
        sleep_time=80 * 86400, discount=0
    )
    user = accounts[0]
    fee_receiver = accounts[3]

    x = market_amm.get_sum_xy(user)[0]

    stablecoin._mint(fee_receiver, x)
    # with pytest.raises(AssertionError, match="Slippage"):
    #     controller.liquidate(fee_receiver, user, x + 1)
    controller.liquidate(fee_receiver, user, int(x * 0.999999))


# @given(frac=st.integers(min_value=10**12, max_value=11 * 10**17))
# @settings(max_examples=200)
# def test_liquidate_callback(accounts, controller_for_liquidation, frac):
#     user = accounts[0]
#     liquidator = accounts[1]
#     fee_receiver = accounts[0]
#     ld = int(0.02 * 1e18)
#     if frac < 10**18:
#         # f = ((1 + h/2) / (1 + h) * (1 - frac) + frac) * frac
#         f = (
#             ((10**18 + ld // 2) * (10**18 - frac) // (10**18 + ld) + frac)
#             * frac
#             // 10**18
#             // 5
#             * 5
#         )  # The latter part is rounding off for multiple bands
#     else:
#         f = 10**18
#     # Partial liquidation improves health.
#     # In case AMM has stablecoins in addition to collateral (our test), it means more stablecoins there.
#     # But that requires more stablecoins than exist.
#     # Therefore, we make more stablecoins if liquidation is partial

#     controller, market_amm, stablecoin = controller_for_liquidation(sleep_time=45 * 86400, discount=0)
#     collateral_token = controller.COLLATERAL_TOKEN

#     # Health here is not too bad, so we still can profitably liquidate
#     x = market_amm.get_sum_xy(user)[0]

#     stablecoin._mint(liquidator, 10**24)

#     # Prepare stablecoins to use for liquidation
#     # we do it by borrowing
#     if f != 10**18:
#         collateral_token._mint(liquidator, 10**18)
#         # collateral_token.approve(controller.address, 2**256-1)
#         debt2 = controller.max_borrowable(10**18, 5)
#         controller.create_loan(liquidator, 10**18, debt2, 5)
#         stablecoin._mint(liquidator, debt2)

#     # with pytest.raises(AssertionError, match="Slippage"):
#     #     controller.liquidate(liquidator, user, x + 1)

#     b = 10**20
#     stablecoin._mint(liquidator, b)
#     health_before = controller.health(user)
#     try:
#         dy = collateral_token.balanceOf[liquidator]
#         controller.liquidate_extended(
#             liquidator, user, int(0.999 * f * x / 1e18), frac, True, None, []
#         )
#         dy = collateral_token.balanceOf[liquidator] - dy
#         dx = stablecoin.balanceOf[liquidator] - b
#         if f > 0:
#             p = market_amm.get_p() / 1e18
#             assert dy * p + dx > 0, "Liquidator didn't make money"
#         if f != 10**18 and f > 0:
#             assert controller.health(user) > health_before
#     except AssertionError as e:
#         if frac == 0 and "Loan doesn't exist" in str(e):
#             pass
#         elif frac * controller.debt(user) // 10**18 == 0:
#             pass
#         else:
#             raise


def test_self_liquidate(accounts, controller_for_liquidation):
    controller, market_amm, stablecoin = controller_for_liquidation(
        sleep_time=int(40 * 86400), discount=2.5 * 10**16
    )
    user = accounts[0]
    fee_receiver = accounts[0]

    stablecoin.transfer(accounts[2], fee_receiver, 10**10)

    x = market_amm.get_sum_xy(user)[0]
    stablecoin.transfer(fee_receiver, user, stablecoin.balanceOf[fee_receiver])

    # stablecoin._mint(accounts[1], 10**24)
    # with pytest.raises(AssertionError, match="Not enough rekt"):
    #     controller.liquidate(accounts[1], user, 0)

    # with pytest.raises(AssertionError, match="Slippage"):
    #     controller.liquidate(user, user, x + 1)

    stablecoin._mint(user, 10**24)
    controller.liquidate(user, user, int(x * 0.999999))


@given(frac=st.integers(min_value=10**14, max_value=10**18 - 13))
def test_tokens_to_liquidate(accounts, controller_for_liquidation, frac):
    user = accounts[0]
    fee_receiver = accounts[0]

    controller, market_amm, stablecoin = controller_for_liquidation(
        sleep_time=80 * 86400, discount=0
    )
    initial_balance = stablecoin.balanceOf[fee_receiver]
    tokens_to_liquidate = controller.tokens_to_liquidate(user, frac)

    stablecoin._mint(fee_receiver, 10**24)

    controller.liquidate_extended(fee_receiver, user, 0, frac, True, None, [])

    balance = stablecoin.balanceOf[fee_receiver]

    if frac < 10**18:
        assert approx(
            balance, initial_balance - tokens_to_liquidate, 1e5, abs_precision=1e5
        )
    else:
        assert balance != initial_balance - tokens_to_liquidate
