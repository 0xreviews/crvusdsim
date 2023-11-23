from curvesim.exceptions import UnregisteredPoolError
from crvusdsim.pool.sim_interface import SimLLAMMAPool


def get_pool_state(pool):
    """
    Returns pool state for the input pool. Functions for each pool type are
    specified in the `pool_state_functions` dict. Each function returns the
    values necessary to reconstruct pool state throughout a simulation run.
    """
    try:
        return pool_state_functions[type(pool)](pool)
    except KeyError as e:
        raise UnregisteredPoolError(
            f"State getter not implemented for pool type '{type(pool)}'."
        ) from e


def get_llamma_pool_state(pool):
    """Returns pool state for llamma pools."""

    last_out_price = pool.price_oracle_contract._price_last / 1e18
    base_price = pool.get_base_price() / 1e18
    (
        bands_x_sum,
        bands_y_sum,
        bands_x_benchmark,
        bands_y_benchmark,
    ) = pool.get_sum_within_fluctuation_range()
    pool_value = bands_x_sum + bands_y_sum * last_out_price
    benchmark_value = bands_x_benchmark + bands_y_benchmark * last_out_price
    arb_profits = pool_value - benchmark_value
    arb_profits_percent = arb_profits / pool_value

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
        "A": pool.A,
        "active_band": pool.active_band,
        "min_band": pool.min_band,
        "max_band": pool.max_band,
        "base_price": base_price,
        "rate": pool.rate,
        "rate_mul": pool.rate_mul / 1e18,
        "fee_rate": pool.fee / 1e18,
        "admin_fee_rate": pool.admin_fee,
        "bands_x_sum": bands_x_sum / 1e18,
        "bands_y_sum": bands_y_sum / 1e18,
        "fees_x": sum(pool.bands_fees_x.values()) / 1e18,
        "fees_y": sum(pool.bands_fees_y.values()) / 1e18,
        "admin_fees_x": pool.admin_fees_x / 1e18,
        "admin_fees_y": pool.admin_fees_y / 1e18,
        "oracle_price": pool.price_oracle() / 1e18,
        "last_out_price": last_out_price,
        "bands_x_benchmark": bands_x_benchmark / 1e18,
        "bands_y_benchmark": bands_y_benchmark / 1e18,
        "pool_value": pool_value / 1e18,
        "benchmark_value": benchmark_value / 1e18,
        "arb_profits": arb_profits / 1e18,
        "arb_profits_percent": arb_profits_percent,
        "bands_arb_profits": bands_arb_profits,
    }


pool_state_functions = {
    SimLLAMMAPool: get_llamma_pool_state,
}
