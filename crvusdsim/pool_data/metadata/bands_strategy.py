"""
Strategies for adjusting band liquidity distribution
"""

from collections import defaultdict
from math import floor, log

from crvusdsim.pool.sim_interface.llamma import SimLLAMMAPool


def simple_bands_strategy(
    pool: SimLLAMMAPool, init_price, max_price, min_price, total_y=10**24
):
    A = pool.A

    base_price = pool.get_base_price()
    init_index = floor(log(init_price / base_price, (A - 1) / A))
    min_index = floor(log(max_price / base_price, (A - 1) / A))
    max_index = floor(log(min_price / base_price, (A - 1) / A))

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
    if sum(pool.bands_x.values()) > 0:
        pool.BORROWED_TOKEN._mint(pool.address, sum(pool.bands_x.values()))
    if sum(pool.bands_y.values()) > 0:
        pool.COLLATERAL_TOKEN._mint(pool.address, sum(pool.bands_y.values()))
