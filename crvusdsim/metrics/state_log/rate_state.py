from crvusdsim.pool import SimMarketInstance
import numpy as np

ONE_YEAR = 365 * 86400

def get_rate_state(sim_market: SimMarketInstance):
    controller = sim_market.controller
    rate0 = sim_market.policy.rate0
    rate = sim_market.policy.rate(controller)
    annualized_rate = (1 + rate / 1e18) ** ONE_YEAR - 1
    pk_debt = sum([pk.debt for pk in sim_market.peg_keepers]) / 1e18
    total_debt = sim_market.factory.total_debt() / 1e18
    pegkeeper_filling = pk_debt / total_debt if total_debt > 0 else 0
    stableswap_mean_price = (
        np.mean([spool.get_p() for spool in sim_market.stableswap_pools]) / 1e18
    )
    agg_price = sim_market.aggregator.price() / 1e18

    return {
        "rate0": rate0,
        "rate": rate,
        "annualized_rate": annualized_rate,
        "pk_debt": pk_debt,
        "total_debt": total_debt,
        "pegkeeper_filling": pegkeeper_filling,
        "stableswap_mean_price": stableswap_mean_price,
        "agg_price": agg_price,
    }
