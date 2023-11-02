"""
Strategies for adjusting band liquidity distribution
"""

from collections import defaultdict
from math import floor, isqrt, log, log2, sqrt
from crvusdsim.pool.crvusd.controller import Controller
from crvusdsim.pool.crvusd.vyper_func import unsafe_sub
from crvusdsim.pool.sim_interface.sim_controller import SimController

from crvusdsim.pool.sim_interface.sim_llamma import SimLLAMMAPool

DEFAULT_USER_ADDRESS = "default_user_address"


def simple_bands_strategy(
    pool: SimLLAMMAPool,
    prices,
    controller,
    parameters,
):
    """
    The strategy used to initial the LLAMMA pool with empty liquidity.

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

    # reset controller loans
    controller.n_loans = 0

    init_price = prices.iloc[0, :].tolist()[0] * 10**18
    # max_price = int(prices.iloc[0,0] * 10**18)
    max_price = int(prices.iloc[:, 0].max() * 10**18)
    min_price = int(prices.iloc[:, 0].min() * 10**18)

    base_price = pool.get_base_price()
    init_index = floor(log(init_price / base_price, (A - 1) / A))
    min_index = floor(log(max_price / base_price, (A - 1) / A))
    max_index = floor(log(min_price / base_price, (A - 1) / A))

    pool.active_band = init_index
    pool.max_band = max_index
    pool.min_band = min_index

    bands_x = defaultdict(int)
    bands_y = defaultdict(int)
    pool.bands_x = bands_x
    pool.bands_y = bands_y

    p_up = pool.p_oracle_up(pool.active_band)
    p_down = pool.p_oracle_down(pool.active_band)
    assert init_price <= p_up and init_price >= p_down

    pool.price_oracle_contract._price_last = init_price
    pool.price_oracle_contract._price_oracle = init_price
    pool.prepare_for_run(prices)


def one_user_bands_strategy(
    pool: SimLLAMMAPool,
    prices,
    controller,
    parameters,
):
    """
    The strategy used to initial the LLAMMA pool with empty liquidity
    and create_loan with one user.

    Parameters
    ----------
    pool : SimLLAMMAPool
        LLAMMA pool
    prices: DataFrame
        prices data
    controller : Controller
        Controller, default is None
    """
    simple_bands_strategy(pool, prices, controller, parameters)

    pool.min_band = pool.active_band

    init_price = prices.iloc[0, :].tolist()[0]
    N = parameters["N"]
    user_address: str = DEFAULT_USER_ADDRESS
    collateral: int = 100 * 10**18
    max_debt = controller.max_borrowable(collateral, N, 0)
    count = 100

    for i in range(count):
        user_address = "%s_%d" % (DEFAULT_USER_ADDRESS, i)
        debt = int(max_debt * (1 - 0.005 * i))

        controller.COLLATERAL_TOKEN._mint(user_address, collateral)
        controller.create_loan(user_address, collateral, debt, N)

    assert (
        pool.COLLATERAL_TOKEN.balanceOf[pool.address] == collateral * count
    ), "deposit collateral faild."


def init_y_bands_strategy(
    pool: SimLLAMMAPool,
    prices,
    controller,
    parameters,
):
    """
    The strategy used to distribute the initial liquidity of the LLAMMA pool
    calculates the x and y amount of each band based on the price fluctuation
    range and the initial price. When price moves one unit, the liquidity
    involved in the exchange is equal to `y_per_one`.

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

    init_price = prices.iloc[0, :].tolist()[0] * 10**18
    # max_price = int(prices.iloc[0,0] * 10**18)
    max_price = int(prices.iloc[:, 0].max() * 10**18)
    min_price = int(prices.iloc[:, 0].min() * 10**18)

    base_price = pool.get_base_price()
    # init_index = floor(log(init_price / base_price, (A - 1) / A))
    min_index = floor(log(max_price / base_price, (A - 1) / A))
    max_index = floor(log(min_price / base_price, (A - 1) / A))

    pool.active_band = min_index
    pool.max_band = max_index
    pool.min_band = min_index
    total_N = max_index - min_index + 1

    bands_x = defaultdict(int)
    bands_y = defaultdict(int)

    init_y = int(sum(pool.bands_x.values()) / prices.iloc[0, 0]) + sum(
        pool.bands_y.values()
    )
    if init_y < 10**18:
        init_y = 10**24

    y_per_price = init_y / (max_price - min_price)

    for i in range(total_N):
        band_index = min_index + i
        price_range = pool.p_oracle_up(band_index) - pool.p_oracle_down(band_index)
        bands_y[band_index] = int(price_range * y_per_price)

    pool.bands_x = bands_x
    pool.bands_y = bands_y

    pool.prepare_for_run(prices)

    if sum(pool.bands_y.values()) > 0:
        pool.COLLATERAL_TOKEN._mint(pool.address, sum(pool.bands_y.values()))

    # Adjust the x and y in the active band
    # so that the amm quotation is consistent with p out
    pool_value_before = (
        sum(pool.bands_x.values()) + sum(pool.bands_y.values()) * init_price / 10**18
    )
    p_o = pool.price_oracle()

    p = pool.p_oracle_up(pool.min_band)
    pool.price_oracle_contract._price_last = p
    pool.price_oracle_contract._price_oracle = p

    while p > init_price:
        p -= int(0.5 * 10**18)
        p = int(max(init_price, p))
        pool.price_oracle_contract._price_last = p
        pool.price_oracle_contract._price_oracle = p

        amount, pump = pool.get_amount_for_price(p)

        if pump:
            i, j = 0, 1
        else:
            i, j = 1, 0

        pool.trade(i, j, amount)

    p_up = pool.p_oracle_up(pool.active_band)
    p_down = pool.p_oracle_down(pool.active_band)

    assert init_price <= p_up and init_price >= p_down

    assert abs(pool.get_p() / p_o - 1) < 5e-3, "init pool price faild."

    # calc band liquidity ratio at both ends of the ending
    # within the price fluctuation range.
    min_band_p_up = pool.p_oracle_up(pool.min_band)
    min_band_p_down = pool.p_oracle_down(pool.min_band)
    pool.min_band_liquidity_scale = (max_price - min_band_p_down) / (
        min_band_p_up - min_band_p_down
    )

    max_band_p_up = pool.p_oracle_up(pool.max_band)
    max_band_p_down = pool.p_oracle_down(pool.max_band)
    pool.max_band_liquidity_scale = (max_band_p_up - min_price) / (
        max_band_p_up - max_band_p_down
    )

    # Adjust x of bands which greater than active_band
    if pool.active_band > pool.min_band:
        pool_value_after = (
            sum(pool.bands_x.values())
            + sum(pool.bands_y.values()) * init_price / 10**18
        )
        x_adjust_per_band = int(
            (pool_value_before - pool_value_after) / (pool.active_band - pool.min_band)
        )
        for i in range(pool.min_band, pool.active_band):
            pool.bands_x[i] += x_adjust_per_band
            pool.bands_x_benchmark[i] += x_adjust_per_band

    bands_x_sum, bands_y_sum, _, _ = pool.get_sum_within_fluctuation_range()
    assert (
        abs((bands_x_sum * 10**18 / init_price + bands_y_sum) / init_y - 1) < 0.05
    ), "y0 changed too much"

    pool.prepare_for_run(prices)


def user_loans_strategy(
    pool: SimLLAMMAPool,
    prices,
    controller: SimController,
    parameters,
    total_y=10**22,
    # users_health=[0.05, 0.06, 0.07],
    # users_count=[2, 3, 4],
):
    """
    The strategy used to distribute the initial liquidity of the LLAMMA pool
    calculates the x and y amount of each band based on the price fluctuation
    range and the initial price. When price moves one unit, the liquidity
    involved in the exchange is equal to `y_per_one`.

    Parameters
    ----------
    pool : SimLLAMMAPool
        LLAMMA pool
    prices: DataFrame
        prices data
    controller : Controller
        Controller, default is None
    total_y: int
        Total initial liquidity (y)
    users_health: List[float]
        User health distribution
    users_count: List[int]
        Distribution of users of different health
    """

    # assert len(users_health) == len(users_count)

    # init pool state
    # set active_band greater than max_price
    A = pool.A

    init_price = prices.iloc[0, :].tolist()[0] * 10**18
    max_price = int(prices.iloc[:, 0].max() * 10**18)
    min_price = int(prices.iloc[:, 0].min() * 10**18)

    base_price = pool.get_base_price()
    init_index = floor(log(init_price / base_price, (A - 1) / A))
    min_index = floor(log(max_price / base_price, (A - 1) / A))
    max_index = floor(log(min_price / base_price, (A - 1) / A)) + 1

    pool.active_band = min_index - 1

    p = pool.p_oracle_up(pool.active_band)
    pool.price_oracle_contract._price_last = p
    pool.price_oracle_contract._price_oracle = p

    # reset controller
    controller.n_loans = 0

    total_users = 20
    y_per_user = total_y / total_users
    N = max_index - min_index + 1

    for i in range(total_users):
        address = "user_%d" % (i)
        collateral_amount = int(y_per_user)
        max_debt = controller.max_borrowable(collateral_amount, N, 0)
        pool.COLLATERAL_TOKEN.mint(address, collateral_amount)
        controller.create_loan(
            address, collateral_amount, int(max_debt * (1 - i * 0.05 / total_users)), N
        )

    # set users' loan
    # total_users = sum(users_count)
    # y_per_user = total_y / total_users
    # count = 0
    # N = max_index - min_index + 1

    # for i in range(len(users_health)):
    #     collateral_amount = int(y_per_user)
    #     max_debt = controller.max_borrowable(collateral_amount, N, 0)

    #     for j in range(users_count[i]):
    #         address = "user_%d_health_%.2f" % (count, users_health[i])
    #         pool.COLLATERAL_TOKEN.mint(address, collateral_amount)
    #         controller.create_loan(address, collateral_amount, max_debt, N)
    #         collateral_value = pool.get_x_down(address)
    #         debt_value = controller.debt(address)

    #         target_debt = int(
    #             collateral_value
    #             * (10**18 - controller.liquidation_discount)
    #             / (users_health[i] * 10**18 + 10**18)
    #         )

    #         # change user's `initial_debt` directly
    #         # (user's range will change if use `repay` or `borrow_more`)
    #         controller.loan[address].initial_debt = target_debt
    #         if debt_value > target_debt:
    #             controller.STABLECOIN.transferFrom(address, controller.address, (debt_value - target_debt))
    #         else:
    #             controller.STABLECOIN.transferFrom(controller.address, address, (target_debt - debt_value))

    #         assert abs(controller.health(address) / 1e18 / users_health[i] - 1) < 1e-3

    #         count += 1

    pool.active_band = pool.min_band
    p = pool.p_oracle_up(pool.active_band)
    pool.price_oracle_contract._price_last = p
    pool.price_oracle_contract._price_oracle = p

    while p > init_price:
        p -= 10**18
        p = int(max(init_price, p))
        pool.price_oracle_contract._price_last = p
        pool.price_oracle_contract._price_oracle = p

        amount, pump = pool.get_amount_for_price(p)

        if pump:
            i, j = 0, 1
        else:
            i, j = 1, 0

        pool.trade(i, j, amount)

    p_up = pool.p_oracle_up(pool.active_band)
    p_down = pool.p_oracle_down(pool.active_band)

    assert init_price <= p_up and init_price >= p_down
