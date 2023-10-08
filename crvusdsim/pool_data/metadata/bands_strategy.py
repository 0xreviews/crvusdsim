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
    A = pool.A

    init_price = prices.iloc[0, :].tolist()[0] * 10**18
    max_price = int(prices.iloc[:, 0].max() * 10**18)
    min_price = int(prices.iloc[:, 0].min() * 10**18)

    base_price = pool.get_base_price()
    init_index = floor(log(init_price / base_price, (A - 1) / A))
    min_index = floor(log(max_price / base_price, (A - 1) / A))
    max_index = floor(log(min_price / base_price, (A - 1) / A)) + unuse_bands

    p_up = pool.p_oracle_up(init_index)
    p_down = pool.p_oracle_up(init_index + 1)

    assert init_price <= p_up
    assert init_price >= p_down

    pool.active_band = init_index
    pool.max_band = max_index
    pool.min_band = min_index
    total_N = max_index - min_index + 1

    bands_x = defaultdict(int)
    bands_y = defaultdict(int)

    per_y = total_y // total_N

    for i in range(total_N):
        bands_y[min_index + i] = per_y

    pool.bands_x = bands_x
    pool.bands_y = bands_y

    pool.prepare_for_run(prices)
    active_band = pool.active_band
    before_active_y_up = pool.get_band_xy_up(
        active_band, pool.bands_x[active_band], pool.bands_y[active_band], use_y=True
    )

    if init_index > min_index:
        for i in range(min_index, init_index):
            p_o_up = pool.p_oracle_up(i)
            p_o_down = pool.p_oracle_down(i)
            # x_down = pool.get_band_xy_up(
            #     i, pool.bands_x[i], pool.bands_y[i], use_y=False, p_o=p_o_down
            # )
            x_down = int(pool.bands_y[i] * (p_o_down + p_o_up) / 2 / 1e18)
            pool.bands_x[i] = x_down
            pool.bands_y[i] = 0

    # Adjust the x and y in the active band
    # so that the amm quotation is consistent with p out
    p_o = pool.price_oracle()
    fee_rate = pool.dynamic_fee()

    # get amount for price (with fee)
    amount, pump = pool.get_amount_for_price(p_o)

    if pump:
        i, j = 0, 1
    else:
        i, j = 1, 0

    amount_in, amount_out, fees = pool.get_dxdy(i, j, amount)
    amount_in = amount_in * unsafe_sub(10**18, fee_rate) // 10**18  # (without fee)

    if pump:
        pool.bands_x[active_band] += amount_in
        pool.bands_y[active_band] -= amount_out
    else:
        pool.bands_y[active_band] += amount_in
        pool.bands_x[active_band] -= amount_out

    after_active_y_up = pool.get_band_xy_up(
        active_band, pool.bands_x[active_band], pool.bands_y[active_band], use_y=True
    )

    assert abs(after_active_y_up / before_active_y_up - 1) < 1e-3, "y0 changed too much"

    # p_o = p_o / 1e18
    # y0 = per_y / 1e18
    # inv = p_o * pool.A**2 * y0**2
    # f = p_o ** 2 / (p_up / 1e18) * pool.A * y0
    # g = (p_up / 1e18) / p_o * (pool.A - 1) * y0
    # x = (inv * p_o)**0.5 - f
    # y = inv / (f + x) - g

    # assert abs((f+x)*(g+y) / inv - 1) < 1e-3

    # pool.bands_x[pool.active_band] = int(x * 1e18)
    # pool.bands_y[pool.active_band] = int(y * 1e18)

    assert abs(pool.get_p() / p_o - 1) < 1e-3, "init pool price faild."

    if sum(pool.bands_x.values()) > 0:
        pool.BORROWED_TOKEN._mint(pool.address, sum(pool.bands_x.values()))
    if sum(pool.bands_y.values()) > 0:
        pool.COLLATERAL_TOKEN._mint(pool.address, sum(pool.bands_y.values()))

    pool.prepare_for_run(prices)
