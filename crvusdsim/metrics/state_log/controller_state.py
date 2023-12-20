from curvesim.exceptions import UnregisteredPoolError
from crvusdsim.pool.sim_interface import SimLLAMMAPool


def get_controller_state(pool, controller):
    """Returns controller and users state."""

    users = list(controller.loans.values())
    users_liquidated = list(controller.users_liquidated.keys())
    
    users_debt = []
    users_x = []
    users_y = []
    users_health = []
    users_init_y = []

    liquidation_volume = 0

    for user_address in users:
        users_debt.append(controller.debt(user_address))
        users_x.append(pool.get_xy_up(user_address, use_y=False) / 1e18)
        users_y.append(pool.get_xy_up(user_address, use_y=True) / 1e18)
        users_health.append(controller.health(user_address) / 1e18)
        users_init_y.append(controller.loan[user_address].initial_collateral / 1e18)
    
    for user_address in users_liquidated:
        liquidated_position = controller.users_liquidated[user_address]
        users_debt.append(0)
        users_x.append(liquidated_position.initial_debt / 1e18)
        users_y.append(0)
        users_health.append(liquidated_position.health / 1e18)
        users_init_y.append(liquidated_position.init_collateral / 1e18)
        liquidation_volume += liquidated_position.initial_debt / 1e18

    liquidation_count = len(users_liquidated)
    
    last_out_price = pool.price_oracle_contract._price_last / 1e18
    base_price = pool.get_base_price() / 1e18

    bands_arb_profits = []
    for band_index in range(pool.min_band, pool.max_band + 1):
        band_value = (
            pool.bands_x[band_index] + pool.bands_y[band_index] * last_out_price
        )
        if band_value > 0:
            band_value_benchmark = (
                pool.bands_x_benchmark[band_index]
                + pool.bands_y_benchmark[band_index] * last_out_price
            )
            bands_arb_profits.append((band_value_benchmark - band_value) / band_value)
        else:
            bands_arb_profits.append(0)

    return {
        # pool state
        "A": controller.A,
        "min_band": pool.min_band,
        "max_band": pool.max_band,
        "base_price": base_price,
        "bands_arb_profits": bands_arb_profits,
        
        # controller state
        "loan_discount": controller.loan_discount / 1e18,
        "liquidation_discount": controller.liquidation_discount / 1e18,
        "initial_debt": controller._total_debt.initial_debt / 1e18,
        "rate_mul": controller._total_debt.rate_mul / 1e18,

        # users state
        "users": users + users_liquidated,
        "users_x": users_x,
        "users_y": users_y,
        "users_health": users_health,
        "users_init_y": users_init_y,
        "users_value": sum(pool.bands_y.values()) / 1e18 * last_out_price + sum(pool.bands_x.values()) / 1e18,

        # liquidation
        "liquidation_count": liquidation_count,
        "liquidation_volume": liquidation_volume,
    }
