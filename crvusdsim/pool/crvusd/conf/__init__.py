__all__ = [
    "STABLECOIN_TOKEN_CONF",
    "LLAMMA_POOL_CONF",
    "STABLE_SWAP_CONF",
    "MONETARY_POLICY_CONF",
    "CONTROLLER_CONF",
    "PEG_KEEPER_CONF",
    "AGGREGATOR_CONF",
    "ARBITRAGUR_ADDRESS",
]


STABLECOIN_TOKEN_CONF = {
    "address": "0xf939e0a03fb07f59a73314e73794be0e57ac1b4e",
    "symbol": "crvUSD",
    "name": "crvUSD",
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

ARBITRAGUR_ADDRESS = "ARBITRAGUR"

LLAMMA_WETH = "0x1681195c176239ac5e72d9aebacf5b2492e0c4ee"
LLAMMA_WBTC = "0xe0438eb3703bf871e31ce639bd351109c88666ea"
LLAMMA_SFRXETH = "0xfa96ad0a9e64261db86950e2da362f5572c5c6fd"
LLAMMA_WSTETH = "0x37417b2238aa52d0dd2d6252d989e728e8f706e4"
LLAMMA_TBTC = "0xf9bd9da2427a50908c4c6d1599d8e62837c2bcb0"

ALIAS_TO_ADDRESS = {
    "crvUSD": "0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E",
    "wstETH": "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0",
    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "TUSD": "0x0000000000085d4780B73119b644AE5ecd22b376",
    "USDP": "0x8E870D67F660D95d5be530380D0eC0bd388289E1",
    "llamma_sfrxeth_v1": "0x136e783846ef68c8bd00a3369f787df8d683a696",
    "llamma_sfrxeth": LLAMMA_SFRXETH,
    "llamma_sfrxeth_v2": LLAMMA_SFRXETH,
    "llamma_wsteth": LLAMMA_WSTETH,
    "llamma_weth": LLAMMA_WETH,
    "llamma_wbtc": LLAMMA_WBTC,
    "llamma_tbtc": LLAMMA_TBTC,
}
