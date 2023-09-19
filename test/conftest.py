import pytest
from math import log

from crvusdsim.pool.crvusd.LLAMMA import LLAMMAPool
from crvusdsim.pool.crvusd.controller_factory import ControllerFactory
from crvusdsim.pool.crvusd.mpolicies.monetary_policy import MonetaryPolicy
from crvusdsim.pool.crvusd.price_oracle.aggregate_stable_price import (
    AggregateStablePrice,
)
from crvusdsim.pool.crvusd.price_oracle.price_oracle import PriceOracle
from crvusdsim.pool.crvusd.stabilizer.peg_keeper import PegKeeper
from crvusdsim.pool.crvusd.stableswap import ARBITRAGUR, LP_PROVIDER, CurveStableSwapPool
from crvusdsim.pool.crvusd.stablecoin import StableCoin

INIT_PRICE = 3000 * 10**18

# LLAMMA
LLAMMA_A = 100
LLAMMA_FEE = 10**16
LLAMMA_ADMIN_FEE = 0

# StableSwap
STABLE_COINS = ["USDC", "USDT", "USDP", "TUSD"]
STABLE_N = 2
STABLE_A = 500  # initially, can go higher later
STABLE_FEE = 1000000  # 0.01%
STABLE_ASSET_TYPE = 0
STABLE_MA_EXP_TIME = 866  # 10 min / ln(2)
STABLE_BALANCES = [10**6 * 10**18] * STABLE_N
# factory
FEE_RECEIVER_DEFAULT = "FEE_RECEIVER_DEFAULT"
# policy
POLICY_RATE0 = int(
    (1.1 ** (1 / (365 * 86400)) - 1) * 1e18
)  # 10% if PegKeepers are empty, 4% when at target fraction
POLICY_SIGMA = 2 * 10**16  # 2% when at target debt fraction
POLICY_DEBT_FRACTION = 10 * 10**16  # 10%
# controller
MARKET_LOAN_DISCOUNT = 9 * 10**16  # 9%; +2% from 4x 1% bands = 100% - 11% = 89% LTV
MARKET_LIQUIDATION_DISCOUNT = 6 * 10**16  # 6%
MARKET_DEBT_CEILING = 10**7 * 10**18  # 10M
# PegKeepers
PEG_KEEPER_CALLER_SHARE = 2 * 10**4
PEG_KEEPER_RECEIVER = "PEG_KEEPER_RECEIVER"
PEG_KEEPER_ADMIN = "PEG_KEEPER_ADMIN"
INIT_PEG_KEEPER_CEILING = MARKET_DEBT_CEILING // len(STABLE_COINS)

# Aggregator
AGGREGATOR_SIGMA = 10**15



@pytest.fixture(scope="module")
def accounts():
    return ["user_address_%d" % i for i in range(5)]


@pytest.fixture(scope="module")
def stablecoin(accounts):
    coin = StableCoin()
    coin._mint(LP_PROVIDER, 10**6 * 10**18)
    coin._mint(ARBITRAGUR, 10**6 * 10**18)
    for addr in accounts:
        coin._mint(addr, 5 * 10**4 * 10**18)
    return coin


@pytest.fixture(scope="module")
def collateral():
    return {
        "symbol": "wstETH",
        "address": "wstETH address",
        "precision": 1,
    }


@pytest.fixture(scope="module")
def price_oracle():
    return PriceOracle(INIT_PRICE)


@pytest.fixture(scope="module")
def other_coins(accounts):
    coins = []
    for symbol in STABLE_COINS:
        _coin = StableCoin(
            address="%s_address" % (symbol),
            symbol=symbol,
            name="%s" % (symbol),
            decimals=18,
        )
        _coin._mint(LP_PROVIDER, 10**6 * 10**18)
        _coin._mint(ARBITRAGUR, 10**6 * 10**18)
        for user in accounts:
            _coin._mint(user, 5 * 10**4 * 10**18)
        coins.append(_coin)

    return coins


@pytest.fixture(scope="module")
def stableswaps(stablecoin, other_coins):
    pools = []
    for peg_coin in other_coins:
        _pool = CurveStableSwapPool(
            name="crvUSD/%s" % (peg_coin.symbol),
            symbol="crvUSD-%s" % (peg_coin.symbol),
            A=STABLE_A,
            D=STABLE_BALANCES.copy(),
            n=STABLE_N,
            fee=STABLE_FEE,
            coins=[peg_coin, stablecoin],
        )
        pools.append(_pool)

    return pools


@pytest.fixture(scope="module")
def aggregator(stablecoin, stableswaps):
    _aggregator = AggregateStablePrice(
        stablecoin=stablecoin,
        sigma=AGGREGATOR_SIGMA,
        admin="",
    )
    for pool in stableswaps:
        _aggregator.add_price_pair(pool)
    return _aggregator


@pytest.fixture(scope="module")
def pegkeepers(factory, aggregator, stableswaps):
    keepers = []
    for pool in stableswaps:
        pk = PegKeeper(
            _pool=pool,
            _index=1,
            _caller_share=PEG_KEEPER_CALLER_SHARE,
            _factory=factory,
            _aggregator=aggregator,
            _receiver=PEG_KEEPER_RECEIVER,
            _admin=PEG_KEEPER_ADMIN,
        )
        factory.set_debt_ceiling(pk.address, INIT_PEG_KEEPER_CEILING)
        keepers.append(pk)
    return keepers


@pytest.fixture(scope="module")
def factory(stablecoin) -> ControllerFactory:
    return ControllerFactory(
        stablecoin=stablecoin,
        fee_receiver=FEE_RECEIVER_DEFAULT,
    )


@pytest.fixture(scope="module")
def monetary_policy(price_oracle, pegkeepers, factory):
    return MonetaryPolicy(
        price_oracle_contract=price_oracle,
        controller_factory_contract=factory,
        peg_keepers=pegkeepers,
        rate0=POLICY_RATE0,
        sigma=POLICY_SIGMA,
        target_debt_fraction=POLICY_DEBT_FRACTION,
    )
