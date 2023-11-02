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


    return {
        # controller state
        "A": controller.A,
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

        # liquidation
        "liquidation_count": liquidation_count,
        "liquidation_volume": liquidation_volume,
    }
