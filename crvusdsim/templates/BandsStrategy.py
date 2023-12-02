
from math import floor, isqrt, log, log2, sqrt
from abc import ABC, abstractmethod
from pandas import DataFrame
from crvusdsim.pool.sim_interface.sim_llamma import SimLLAMMAPool

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