import pytest
from hypothesis import settings
from hypothesis import HealthCheck
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    run_state_machine_as_test,
    rule,
    invariant,
    initialize,
)
from hypothesis import Phase

from crvusdsim.pool.crvusd.LLAMMA import LLAMMAPool
from crvusdsim.pool.crvusd.price_oracle.price_oracle import PriceOracle
from crvusdsim.pool.crvusd.stablecoin import StableCoin
from crvusdsim.pool.crvusd.utils.ERC20 import ERC20
from test.conftest import INIT_PRICE, LLAMMA_A, LLAMMA_ADMIN_FEE, LLAMMA_FEE


def get_borrowed_token(borrowed_digits):
    return StableCoin(decimals=borrowed_digits)


def get_collateral_token(collateral_digits):
    return ERC20(
        address="wstETH_address",
        name="Wrapped stETH",
        symbol="wstETH",
        decimals=collateral_digits,
    )


def get_amm(collateral_token, borrowed_token):
    price_oracle = PriceOracle(INIT_PRICE)
    amm = LLAMMAPool(
        A=LLAMMA_A,
        BASE_PRICE=INIT_PRICE,
        fee=LLAMMA_FEE,
        admin_fee=LLAMMA_ADMIN_FEE,
        price_oracle_contract=price_oracle,
        collateral=collateral_token,
        borrowed_token=borrowed_token,
    )
    return amm


class StatefulExchange(RuleBasedStateMachine):
    amounts = st.lists(
        st.integers(min_value=0, max_value=10**6 * 10**18), min_size=5, max_size=5
    )
    ns = st.lists(st.integers(min_value=1, max_value=20), min_size=5, max_size=5)
    dns = st.lists(st.integers(min_value=0, max_value=20), min_size=5, max_size=5)
    amount = st.integers(min_value=0, max_value=10**9 * 10**18)
    pump = st.booleans()
    user_id = st.integers(min_value=0, max_value=4)

    def __init__(self):
        super().__init__()
        self.total_deposited = 0

    @initialize(amounts=amounts, ns=ns, dns=dns)
    def initializer(self, amounts, ns, dns):
        self.borrowed_token = get_borrowed_token(self.borrowed_digits)
        self.collateral_token = get_collateral_token(self.collateral_digits)
        self.amm = get_amm(self.collateral_token, self.borrowed_token)

        self.borrowed_mul = 10 ** (18 - self.borrowed_digits)
        self.collateral_mul = 10 ** (18 - self.collateral_digits)
        amounts = [a // self.collateral_mul for a in amounts]
        for user, amount, n1, dn in zip(self.accounts, amounts, ns, dns):
            n2 = n1 + dn
            try:
                self.amm.deposit_range(user, amount, n1, n2)
                self.collateral_token._mint(self.amm.address, amount)
            except Exception as e:
                if "Amount too low" in str(e):
                    assert amount // (dn + 1) <= 100
                else:
                    raise
        self.total_deposited = sum(self.amm.bands_y[n] for n in range(42))

    @rule(amount=amount, pump=pump, user_id=user_id)
    def exchange(self, amount, pump, user_id):
        u = self.accounts[user_id]
        if pump:
            amount = amount // self.borrowed_mul
            i = 0
            j = 1
            in_token = self.borrowed_token
        else:
            amount = amount // self.collateral_mul
            i = 1
            j = 0
            in_token = self.collateral_token
        u_amount = in_token.balanceOf[u]
        if amount > u_amount:
            in_token._mint(u, amount - u_amount)
        self.amm.exchange(i, j, amount, 0, _receiver=u)

    @invariant()
    def amm_solvent(self):
        X = sum(self.amm.bands_x[n] for n in range(42))
        Y = sum(self.amm.bands_y[n] for n in range(42))
        assert self.borrowed_token.balanceOf[self.amm.address] * self.borrowed_mul >= X
        assert (
            self.collateral_token.balanceOf[self.amm.address] * self.collateral_mul >= Y
        )

    @invariant()
    def dy_back(self):
        n = self.amm.active_band
        to_swap = self.total_deposited * 10 // self.collateral_mul
        left_in_amm = sum(self.amm.bands_y[n] for n in range(42))
        if n < 50:
            dx, dy = self.amm.get_dxdy(1, 0, to_swap)
            assert (
                dx * self.collateral_mul >= self.total_deposited - left_in_amm
            )  # With fees, AMM will have more

    def teardown(self):
        if not hasattr(self, "amm"):
            return
        u = self.accounts[0]
        # Trade back and do the check
        n = self.amm.active_band
        to_swap = self.total_deposited * 10 // self.collateral_mul
        if n < 50:
            _, dy = self.amm.get_dxdy(1, 0, to_swap)
            if dy > 0:
                self.collateral_token._mint(u, to_swap)
                self.amm.exchange(1, 0, to_swap, 0, _receiver=u)
                left_in_amm = sum(self.amm.bands_y[n] for n in range(42))
                assert left_in_amm >= self.total_deposited


@pytest.mark.parametrize("borrowed_digits", [6, 8, 18])
@pytest.mark.parametrize("collateral_digits", [6, 8, 18])
def test_statefull_exchange(accounts, borrowed_digits, collateral_digits):
    StatefulExchange.TestCase.settings = settings(
        max_examples=20,
        stateful_step_count=10,
        phases=(Phase.explicit, Phase.reuse, Phase.generate, Phase.target),
        suppress_health_check=[HealthCheck.data_too_large],
    )
    accounts = accounts[:5]

    for k, v in locals().items():
        setattr(StatefulExchange, k, v)
    run_state_machine_as_test(StatefulExchange)


def test_raise_at_dy_back(accounts):
    accounts = accounts[:5]

    borrowed_digits = 18
    collateral_digits = 18

    for k, v in locals().items():
        setattr(StatefulExchange, k, v)
    state = StatefulExchange()
    state.initializer(
        amounts=[0, 0, 0, 10**18, 10**18], ns=[1, 1, 1, 1, 2], dns=[0, 0, 0, 0, 0]
    )
    state.amm_solvent()
    state.dy_back()
    state.exchange(amount=3123061067055650168655, pump=True, user_id=0)
    state.amm_solvent()
    state.dy_back()
    state.exchange(amount=3123061067055650168655, pump=True, user_id=0)
    state.amm_solvent()
    state.dy_back()
    state.teardown()


def test_raise_rounding(accounts):
    accounts = accounts[:5]

    borrowed_digits = 16
    collateral_digits = 18

    for k, v in locals().items():
        setattr(StatefulExchange, k, v)
    state = StatefulExchange()
    state.initializer(
        amounts=[101, 0, 0, 0, 0], ns=[1, 1, 1, 1, 1], dns=[0, 0, 0, 0, 0]
    )
    state.exchange(amount=100, pump=True, user_id=0)
    state.dy_back()
    state.teardown()


def test_raise_rounding_2(accounts):
    accounts = accounts[:5]

    borrowed_digits = 18
    collateral_digits = 18

    for k, v in locals().items():
        setattr(StatefulExchange, k, v)
    state = StatefulExchange()
    state.initializer(
        amounts=[779, 5642, 768, 51924, 5],
        ns=[2, 3, 4, 10, 18],
        dns=[11, 12, 14, 15, 15],
    )
    state.amm_solvent()
    state.dy_back()
    state.exchange(amount=42, pump=True, user_id=1)
    state.amm_solvent()
    state.dy_back()
    state.exchange(amount=512, pump=True, user_id=2)
    state.amm_solvent()
    state.dy_back()
    state.teardown()


def test_raise_rounding_3(accounts):
    accounts = accounts[:5]

    borrowed_digits = 17
    collateral_digits = 18

    for k, v in locals().items():
        setattr(StatefulExchange, k, v)
    state = StatefulExchange()
    state.initializer(
        amounts=[33477, 63887, 387, 1, 0], ns=[4, 18, 6, 19, 5], dns=[18, 0, 8, 20, 5]
    )
    state.amm_solvent()
    state.dy_back()
    state.exchange(amount=22005, pump=False, user_id=2)
    state.amm_solvent()
    state.dy_back()
    state.exchange(amount=184846817736507205598398482, pump=False, user_id=4)
    state.amm_solvent()
    state.dy_back()
    state.exchange(amount=140, pump=True, user_id=2)
    state.amm_solvent()
    state.dy_back()
    state.exchange(amount=233, pump=True, user_id=0)
    state.amm_solvent()
    state.dy_back()
    state.exchange(amount=54618, pump=True, user_id=3)
    state.amm_solvent()
    state.dy_back()
    state.exchange(amount=169, pump=True, user_id=3)
    state.amm_solvent()
    state.dy_back()
    state.teardown()
