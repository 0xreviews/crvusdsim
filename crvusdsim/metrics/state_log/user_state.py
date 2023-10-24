from curvesim.exceptions import UnregisteredPoolError
from crvusdsim.pool.sim_interface import SimLLAMMAPool


def get_user_state(pool, controller):
    """Returns user state."""

    users = list(controller.loans.values())
    users_debt = []
    users_x = []
    users_y = []
    users_health = []
    for user_address in users:
        users_debt.append(controller.debt(user_address))
        users_x.append(pool.get_xy_up(user_address, use_y=False) / 1e18)
        users_y.append(pool.get_xy_up(user_address, use_y=True) / 1e18)
        users_health.append(controller.health(user_address) / 1e18)

    return {
        "users": users,
        "users_x": users_x,
        "users_y": users_y,
        "users_health": users_health,
    }
