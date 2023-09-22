__all__ = [
    "STABLECOIN_TOKEN_CONF",
    "LLAMMA_POOL_CONF",
    "STABLE_SWAP_CONF",
    "MONETARY_POLICY_CONF",
    "CONTROLLER_CONF",
    "PEG_KEEPER_CONF",
    "AGGREGATOR_CONF",
]


STABLECOIN_TOKEN_CONF = {
    "address": "0xf939e0a03fb07f59a73314e73794be0e57ac1b4e",
    "symbol": "crvUSD",
    "name": "Curve.Fi USD Stablecoin (crvUSD)",
    "decimals": 18,
}

LLAMMA_POOL_CONF = {
    "A": 100,
    "fee": 10**16,
    "admin_fee": 0,
}

STABLE_SWAP_CONF = {
    "N": 2,
    "A": 500,
    "fee": 1000000,  # 0.01%
    "asset_type": 0,
    "ma_exp_time": 866,  # 10 min / ln(2)
    "balances": [10**6 * 10**18] * 2,
}

MONETARY_POLICY_CONF = {
    "rate0": 2732676751,
    # "rate0": int((1.1**(1 / (365 * 86400)) - 1) * 1e18),  # 10% if PegKeepers are empty, 4% when at target fraction
    "sigma": 2 * 10**16,  # 2% when at target debt fraction
    "fraction": 10 * 10**16,  # 10%
}

CONTROLLER_CONF = {
    "loan_discount": 9 * 10**16,  # 9%; +2% from 4x 1% bands = 100% - 11% = 89% LTV
    "liquidation_discount": 6 * 10**16,  # 6%
    "debt_ceiling": 10**7 * 10**18,  # 10M
}

PEG_KEEPER_CONF = {
    "index": 1,
    "caller_share": 2 * 10**4,
    "receiver": "PEG_KEEPER_RECEIVER",
    "admin": "PEG_KEEPER_ADMIN",
}

AGGREGATOR_CONF = {
    "sigma": 10**15,
}