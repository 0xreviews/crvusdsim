"""
Strategies for adjusting band liquidity distribution
"""

from collections import defaultdict
from math import floor, log
from crvusdsim.pool.crvusd.LLAMMA import LLAMMAPool


def simple_bands_strategy(pool: LLAMMAPool, init_price, total_y=None, total_range=50):

    A = pool.A

    base_price = pool.get_base_price()
    init_index = floor(log(init_price / base_price, (A-1) / A))

    p_up = pool.p_oracle_up(init_index)
    p_down = pool.p_oracle_up(init_index+1)

    assert init_price <= p_up
    assert init_price >= p_down

    print("init_index", init_index)

    pool.active_band = init_index

    bands_x = defaultdict(int)
    bands_y = defaultdict(int)

    if total_y is not None:
        per_y = total_y // total_range
        
        for i in range(total_range):
            bands_y[init_index+i] = per_y

        pool.bands_x = bands_x
        pool.bands_y = bands_y
        if sum(pool.bands_x.values()) > 0:
            pool.BORROWED_TOKEN._mint(pool.address, sum(pool.bands_x.values()))
        if sum(pool.bands_y.values()) > 0:
            pool.COLLATERAL_TOKEN._mint(pool.address, sum(pool.bands_y.values()))

        pool.old_p_o = int(init_price)

