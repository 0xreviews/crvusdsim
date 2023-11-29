"""
Strategies for adjusting band liquidity distribution
"""

from collections import defaultdict
from datetime import timedelta
from math import floor, isqrt, log, log2, sqrt
from abc import ABC, abstractmethod
from pandas import DataFrame
from crvusdsim.pool.crvusd.controller import Controller
from crvusdsim.pool.crvusd.vyper_func import unsafe_sub
from crvusdsim.pool.sim_interface.sim_controller import SimController

from crvusdsim.pool.sim_interface.sim_llamma import SimLLAMMAPool

DEFAULT_USER_ADDRESS = "default_user_address"


class BandsStrategy(ABC):
    def __init__(
        self, pool: SimLLAMMAPool, prices, controller=None, parameters=None, **kwargs
    ):
        """
        Parameters
        ----------
        pool : SimLLAMMAPool
            LLAMMA pool
        prices: DataFrame
            prices data
        controller : Controller
            Controller, default is None
        """

        A = pool.A
        base_price = pool.get_base_price()
        init_price = int(prices.iloc[0, :].tolist()[0] * 10**18)
        max_price = int(prices.iloc[:, 0].max() * 10**18)
        min_price = int(prices.iloc[:, 0].min() * 10**18)
        init_index = floor(log(init_price / base_price, (A - 1) / A))
        min_index = floor(log(max_price / base_price, (A - 1) / A))
        max_index = floor(log(min_price / base_price, (A - 1) / A)) + 1

        if abs(pool.p_oracle_up(min_index) / max_price) - 1 < 5e-3:
            min_index -= 1
        if abs(pool.p_oracle_up(max_index) / min_price) - 1 < 5e-3:
            max_index += 1

        pool.min_band = min_index
        pool.max_band = max_index

        self.pool = pool
        self.prices = prices
        self.controller = controller
        self.parameters = parameters
        self.base_price = base_price
        self.init_price = init_price
        self.max_price = max_price
        self.min_price = min_price
        self.init_index = init_index
        self.min_index = min_index
        self.max_index = max_index

    @abstractmethod
    def do_strategy(self):
        """
        Process the bands strategy to get liquidity.
        """
        raise NotImplementedError

    def find_active_band_by_step(self):
        self.pool.active_band = self.pool.min_band

        for n in range(self.pool.min_band, self.pool.max_band):
            if self.pool.bands_x[n] == 0 and self.pool.bands_y[n] == 0:
                continue
            elif self.pool.bands_x[n] == 0 and self.pool.bands_y[n] > 0:
                self.pool.active_band = n
                break

        assert self.pool.bands_x[self.pool.active_band] == 0
        assert self.pool.bands_y[self.pool.active_band] > 0

        p = self.pool.p_oracle_up(self.pool.active_band)
        self.pool.prepare_for_run(DataFrame([p / 1e18], index=[self.prices.index[0]]))
        delta_p = 1

        while p > self.init_price:
            p -= int(delta_p * 10**18)
            p = int(max(self.init_price, p))
            self.pool.price_oracle_contract._price_last = p
            self.pool.price_oracle_contract._price_oracle = p
            self.pool._increment_timestamp(timedelta=10 * 60)
            self.pool.price_oracle_contract._increment_timestamp(timedelta=10 * 60)

            amount, pump = self.pool.get_amount_for_price(p)
            if amount > 0:
                if pump:
                    i, j = 0, 1
                else:
                    i, j = 1, 0
                self.pool.trade(i, j, amount, snapshot=False)
                if abs(self.pool.get_p() / p) - 1 > 1e-3:
                    delta_p /= 2
                if abs(self.pool.get_p() - p) < 5:
                    delta_p = 0.2

            assert (
                self.pool.active_band <= self.pool.max_band
                and self.pool.active_band >= self.pool.min_band
            ), "init price faild."

        self.pool.prepare_for_run(self.prices)
        amount, pump = self.pool.get_amount_for_price(self.init_price)
        if amount > 0:
            if pump:
                i, j = 0, 1
            else:
                i, j = 1, 0
            self.pool.trade(i, j, amount, snapshot=False)

    def check_active_band_init(self):
        p_up = self.pool.p_oracle_up(self.pool.active_band)
        p_down = self.pool.p_oracle_down(self.pool.active_band)

        assert (
            self.init_price <= p_up * 1.001 and self.init_price >= p_down * 0.999
        ), "init pool active_band faild."

    def check_amm_price_init(self):
        p_o = self.pool.price_oracle()
        amm_p = self.pool.get_p()
        assert abs(amm_p / p_o - 1) < 5e-3, "init pool price faild."


class SimpleUsersBandsStrategy(BandsStrategy):

    def __init__(
        self,
        pool: SimLLAMMAPool,
        prices,
        controller=None,
        parameters=None,
        collateral_amount: int = 10 * 10**18
    ):
        super().__init__(pool, prices, controller, parameters)
        self.collateral_amount = collateral_amount

    def do_strategy(self):
        # reset controller loans
        self.controller.n_loans = 0

        self.pool.active_band = self.init_index
        self.pool.max_band = self.max_index
        self.pool.min_band = self.min_index

        bands_x = defaultdict(int)
        bands_y = defaultdict(int)
        self.pool.bands_x = bands_x
        self.pool.bands_y = bands_y

        self.check_active_band_init()

        self.pool.prepare_for_run(self.prices)

        self.pool.min_band = self.pool.active_band

        N = self.parameters["N"]
        user_address: str = DEFAULT_USER_ADDRESS

        max_debt = self.controller.max_borrowable(self.collateral_amount, N, 0)
        count = 100

        for i in range(count):
            user_address = "%s_%d" % (DEFAULT_USER_ADDRESS, i)
            debt = int(max_debt * (1 - 0.005 * i))

            self.controller.COLLATERAL_TOKEN._mint(user_address, self.collateral_amount)
            self.controller.create_loan(user_address, self.collateral_amount, debt, N)

        assert (
            self.pool.COLLATERAL_TOKEN.balanceOf[self.pool.address]
            == self.collateral_amount * count
        ), "deposit collateral faild."


class IinitYBandsStrategy(BandsStrategy):
    def do_strategy(self):
        self.pool.active_band = self.min_index
        self.pool.max_band = self.max_index
        self.pool.min_band = self.min_index
        total_N = self.max_index - self.min_index + 1

        bands_x = defaultdict(int)
        bands_y = defaultdict(int)

        init_y = int(sum(self.pool.bands_x.values()) / self.prices.iloc[0, 0]) + sum(
            self.pool.bands_y.values()
        )
        if init_y < 10**18:
            init_y = 10**24

        y_per_price = init_y / (self.max_price - self.min_price)

        for i in range(total_N):
            band_index = self.min_index + i
            price_range = self.pool.p_oracle_up(band_index) - self.pool.p_oracle_down(
                band_index
            )
            bands_y[band_index] = int(price_range * y_per_price)

        self.pool.bands_x = bands_x
        self.pool.bands_y = bands_y

        if sum(self.pool.bands_y.values()) > 0:
            self.pool.COLLATERAL_TOKEN._mint(
                self.pool.address, sum(self.pool.bands_y.values())
            )

        # Adjust the x and y in the active band
        # so that the amm quotation is consistent with p out
        pool_value_before = (
            sum(self.pool.bands_x.values())
            + sum(self.pool.bands_y.values()) * self.init_price / 10**18
        )

        self.find_active_band_by_step()

        self.check_active_band_init()

        self.check_amm_price_init()

        # calc band liquidity ratio at both ends of the ending
        # within the price fluctuation range.
        min_band_p_up = self.pool.p_oracle_up(self.pool.min_band)
        min_band_p_down = self.pool.p_oracle_down(self.pool.min_band)
        self.pool.min_band_liquidity_scale = (self.max_price - min_band_p_down) / (
            min_band_p_up - min_band_p_down
        )

        max_band_p_up = self.pool.p_oracle_up(self.pool.max_band)
        max_band_p_down = self.pool.p_oracle_down(self.pool.max_band)
        self.pool.max_band_liquidity_scale = (max_band_p_up - self.min_price) / (
            max_band_p_up - max_band_p_down
        )

        # Adjust x of bands which greater than active_band
        if self.pool.active_band > self.pool.min_band:
            pool_value_after = (
                sum(self.pool.bands_x.values())
                + sum(self.pool.bands_y.values()) * self.init_price / 10**18
            )
            x_adjust_per_band = int(
                (pool_value_before - pool_value_after)
                / (self.pool.active_band - self.pool.min_band)
            )
            for i in range(self.pool.min_band, self.pool.active_band):
                self.pool.bands_x[i] += x_adjust_per_band
                self.pool.bands_x_benchmark[i] += x_adjust_per_band

        bands_x_sum, bands_y_sum, _, _ = self.pool.get_sum_within_fluctuation_range()
        assert (
            abs((bands_x_sum * 10**18 / self.init_price + bands_y_sum) / init_y - 1)
            < 0.05
        ), "y0 changed too much"


class UserLoansBandsStrategy(BandsStrategy):
    def __init__(
        self,
        pool: SimLLAMMAPool,
        prices,
        controller=None,
        parameters=None,
        total_y=10**22,
        total_users=20,
    ):
        super().__init__(pool, prices, controller, parameters)
        self.total_y = total_y
        self.total_users = total_users

    def do_strategy(self):
        self.pool.active_band = self.min_index - 1

        p = self.pool.p_oracle_up(self.pool.active_band)
        self.pool.price_oracle_contract._price_last = p
        self.pool.price_oracle_contract._price_oracle = p

        # reset controller
        self.controller.n_loans = 0

        y_per_user = self.total_y / self.total_users
        N = self.max_index - self.min_index + 1

        for i in range(self.total_users):
            address = "user_%d" % (i)
            collateral_amount = int(y_per_user)
            max_debt = self.controller.max_borrowable(collateral_amount, N, 0)
            self.pool.COLLATERAL_TOKEN.mint(address, collateral_amount)
            self.controller.create_loan(
                address,
                collateral_amount,
                int(max_debt * (1 - i * 0.05 / self.total_users)),
                N,
            )

        self.find_active_band_by_step()

        self.check_active_band_init()

        self.check_amm_price_init()
