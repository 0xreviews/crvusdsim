"""
Strategies for adjusting band liquidity distribution
"""

from collections import defaultdict
from math import floor, log
from crvusdsim.pool.crvusd.vyper_func import unsafe_sub

from crvusdsim.pool.sim_interface.llamma import SimLLAMMAPool


def simple_bands_strategy(
    pool: SimLLAMMAPool,
    prices,
    total_y=10**24,
    unuse_bands=0,
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
    total_y: int
        Total initial liquidity (y)
    unuse_bands: int
        The amount of bands that are smaller than the price fluctuation range and will
        not involved in exchanges
    """
    A = pool.A

    init_price = prices.iloc[0, :].tolist()[0] * 10**18
    max_price = int(prices.iloc[0,0] * 10**18)
    # max_price = int(prices.iloc[:, 0].max() * 10**18)
    min_price = int(prices.iloc[:, 0].min() * 10**18)

    base_price = pool.get_base_price()
    # init_index = floor(log(init_price / base_price, (A - 1) / A))
    min_index = floor(log(max_price / base_price, (A - 1) / A))
    max_index = floor(log(min_price / base_price, (A - 1) / A)) + unuse_bands

    pool.active_band = min_index
    pool.max_band = max_index
    pool.min_band = min_index
    total_N = max_index - min_index + 1

    bands_x = defaultdict(int)
    bands_y = defaultdict(int)

    y_per_price = total_y / (max_price - min_price)

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
    p_o = pool.price_oracle()

    # while True:
    #     amount, pump = pool.get_amount_for_price(p_o)
    #     if pump:
    #         i, j = 0, 1
    #     else:
    #         i, j = 1, 0
    #     amount_in, amount_out, fees = pool.get_dxdy(i, j, amount)
    #     active_index = pool.active_band
    #     if amount_out < pool.bands_y[active_index]:
    #         break
    #     p_o_up = pool.p_oracle_up(active_index)
    #     p_o_down = pool.p_oracle_down(active_index)
    #     x_down = int(pool.bands_y[active_index] * (p_o_down + p_o_up) / 2 / 1e18)
    #     pool.bands_x[active_index] = x_down
    #     pool.bands_y[active_index] = 0
    #     pool.active_band += 1
    #     break

    p = pool.p_oracle_up(pool.min_band)
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

    # get amount for price (with fee)
    amount, pump = pool.get_amount_for_price(p_o)

    if pump:
        i, j = 0, 1
    else:
        i, j = 1, 0

    amount_in, amount_out, fees = pool.get_dxdy(i, j, amount)

    if pump:
        pool.bands_x[pool.active_band] += amount_in - fees
        pool.bands_y[pool.active_band] -= amount_out
        if pool.bands_y[pool.active_band] == 0:
            pool.active_band += 1
    else:
        pool.bands_y[pool.active_band] += amount_in - fees
        pool.bands_x[pool.active_band] -= amount_out
        if pool.bands_x[pool.active_band] == 0:
            pool.active_band -= 1

    assert abs(pool.get_p() / p_o - 1) < 1e-3, "init pool price faild."

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

    bands_x_sum, bands_y_sum, _, _ = pool.get_sum_within_fluctuation_range()

    assert (
        abs((bands_x_sum * 10**18 / init_price + bands_y_sum) / total_y - 1) < 0.03
    ), "y0 changed too much"

    pool.prepare_for_run(prices)
