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
from crvusdsim.pool.crvusd.stableswap import CurveStableSwapPool
from crvusdsim.pool.crvusd.stablecoin import StableCoin

INIT_PRICE = 3000 * 10**18

# LLAMMA
LLAMMA_A = 100
LLAMMA_FEE = 10**16
LLAMMA_ADMIN_FEE = 0

# StableSwap
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
# Aggregator
AGGREGATOR_SIGMA = 10**15


@pytest.fixture(scope="module")
def accounts():
    return ["user_address_%d" % i for i in range(5)]


@pytest.fixture
def stablecoin():
    return StableCoin()


@pytest.fixture
def collateral():
    return {
        "symbol": "wstETH",
        "address": "wstETH address",
        "precision": 1,
    }


@pytest.fixture
def price_oracle():
    return PriceOracle(INIT_PRICE)


@pytest.fixture
def stableswaps(stablecoin):
    pools = []
    for symbol in ["USDC", "USDT", "USDP", "TUSD"]:
        pegged_coin = StableCoin(
            address="%s_address" % (symbol),
            name="%s" % (symbol),
            decimals=18,
        )
        pools.append(
            CurveStableSwapPool(
                name="crvUSD/%s" % (symbol),
                symbol="crvUSD-%s" % (symbol),
                A=STABLE_A,
                D=STABLE_BALANCES,
                n=STABLE_N,
                fee=STABLE_FEE,
                coins=[stablecoin, pegged_coin],
            )
        )
    return pools


@pytest.fixture
def aggregator(stablecoin):
    return AggregateStablePrice(
        stablecoin=stablecoin,
        sigma=AGGREGATOR_SIGMA,
        admin="",
    )


@pytest.fixture
def pegkeepers(factory, aggregator, stableswaps):
    keepers = []
    for pool in stableswaps:
        keepers.append(
            PegKeeper(
                _pool=pool,
                _index=1,
                _caller_share=PEG_KEEPER_CALLER_SHARE,
                _factory=factory,
                _aggregator=aggregator,
                _receiver=PEG_KEEPER_RECEIVER,
                _admin=PEG_KEEPER_ADMIN,
            )
        )
    return keepers


@pytest.fixture
def factory(stablecoin) -> ControllerFactory:
    return ControllerFactory(
        stablecoin=stablecoin,
        fee_receiver=FEE_RECEIVER_DEFAULT,
    )


@pytest.fixture
def monetary_policy(price_oracle, pegkeepers, factory):
    return MonetaryPolicy(
        price_oracle_contract=price_oracle,
        controller_factory_contract=factory,
        peg_keepers=pegkeepers,
        rate0=POLICY_RATE0,
        sigma=POLICY_SIGMA,
        target_debt_fraction=POLICY_DEBT_FRACTION,
    )
