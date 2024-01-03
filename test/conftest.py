from typing import Tuple
import pytest
from math import log

from curvesim.pool.sim_interface import SimCurveCryptoPool
from crvusdsim.pool.crvusd.conf import ARBITRAGUR_ADDRESS
from crvusdsim.pool.crvusd.utils.ERC20 import ERC20
from crvusdsim.pool.crvusd.LLAMMA import LLAMMAPool
from crvusdsim.pool.crvusd.controller_factory import ControllerFactory
from crvusdsim.pool.crvusd.controller import Controller
from crvusdsim.pool.crvusd.mpolicies.monetary_policy import MonetaryPolicy
from crvusdsim.pool.crvusd.price_oracle.aggregate_stable_price import (
    AggregateStablePrice,
)
from crvusdsim.pool.crvusd.price_oracle.price_oracle import PriceOracle
from crvusdsim.pool.crvusd.price_oracle.crypto_with_stable_price import (
    CryptoWithStablePrice
)
from crvusdsim.pool.crvusd.stabilizer.peg_keeper import PegKeeper
from crvusdsim.pool.crvusd.stableswap import LP_PROVIDER, CurveStableSwapPool
from crvusdsim.pool.crvusd.stablecoin import StableCoin
from crvusdsim.pool.sim_interface import SimCurveStableSwapPool

INIT_PRICE = 2000 * 10**18
INIT_PRICE_D1 = INIT_PRICE // 10**18

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
# TriCrypto
TRICRYPTO_COINS = [["USDC", "WBTC", "WETH"], ["USDT", "WBTC", "WETH"]]
TRICRYPTO_A = 1707629
TRICRYPTO_PRECISIONS = [1, 1, 1]
TRICRYPTO_GAMMA = 11809167828997
TRICRYPTO_N_COINS = 3
TRICRYPTO_MID_FEE = 3000000
TRICRYPTO_OUT_FEE = 30000000
TRICRYPTO_ALLOWED_EXTRA_PROFIT = 2000000000000
TRICRYPTO_FEE_GAMMA = 500000000000000
TRICRYPTO_ADJUSTMENT_STEP = 490000000000000
TRICRYPTO_MA_HALF_TIME = 600
TRICRYPTO_PRICE_SCALE = [44912882696470104260465, 2357733641392764512005]
TRICRYPTO_BALANCES = [
    25709017706486000000000000, 
    567766370730000000000, 
    10916847916467958574912
]
TRICRYPTO_KWARGS = {
        "A": TRICRYPTO_A,
        "gamma": TRICRYPTO_GAMMA,
        "n": TRICRYPTO_N_COINS,
        "precisions": TRICRYPTO_PRECISIONS,
        "mid_fee": TRICRYPTO_MID_FEE,
        "out_fee": TRICRYPTO_OUT_FEE,
        "allowed_extra_profit": TRICRYPTO_ALLOWED_EXTRA_PROFIT,
        "fee_gamma": TRICRYPTO_FEE_GAMMA,
        "adjustment_step": TRICRYPTO_ADJUSTMENT_STEP,
        "ma_half_time": TRICRYPTO_MA_HALF_TIME,
        "price_scale": TRICRYPTO_PRICE_SCALE,
        "balances": TRICRYPTO_BALANCES,
}
# Aggregator
AGGREGATOR_SIGMA = 10**15
# Crypto with Stable Price
CRYPTO_WITH_STABLE_PRICE_N = 2
CRYPTO_WITH_STABLE_PRICE_COINS = ["USDC", "USDT"]
CRYPTO_WITH_STABLE_PRICE_IX = {
    "weth": [1, 1],
    "wbtc": [0, 0],
}
CRYPTO_WITH_STABLE_PRICE_COLLAT_IX = {
    "weth": [2, 2],
    "wbtc": [1, 1]
} # TODO is this just ix + 1?

def _create_stablecoin():
    coin = StableCoin()
    coin._mint(LP_PROVIDER, 10**6 * 10**18)
    coin._mint(ARBITRAGUR_ADDRESS, 10**6 * 10**18)
    # for addr in accounts:
    #     coin._mint(addr, 5 * 10**4 * 10**18)
    return coin


def _create_collteral(symbol = "wstETH"):
    coin = ERC20(
        address="%s_address" % (symbol),
        name="%s" % (symbol),
        symbol=symbol,
        decimals=18,
    )
    coin._mint(LP_PROVIDER, 10**6 * 10**18)
    coin._mint(ARBITRAGUR_ADDRESS, 10**6 * 10**18)
    return coin


def _create_other_stablecoin(symbol):
    _coin = StableCoin(
        address="%s_address" % (symbol),
        symbol=symbol,
        name="%s" % (symbol),
        decimals=18,
    )
    _coin._mint(LP_PROVIDER, 10**6 * 10**18)
    _coin._mint(ARBITRAGUR_ADDRESS, 10**6 * 10**18)
    return _coin


def _create_other_coins(other_coins=STABLE_COINS):
    coins = []
    for symbol in other_coins:
        _coin = _create_other_stablecoin(symbol)
        coins.append(_coin)
    return coins


def _create_stableswaps(stablecoin, other_coins, sim = False):
    pools = []
    constructor = CurveStableSwapPool if not sim else SimCurveStableSwapPool
    for peg_coin in other_coins:
        _pool = constructor(
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


def _create_price_oracle():
    return PriceOracle(INIT_PRICE)


def _create_aggregator(stablecoin, stableswaps):
    _aggregator = AggregateStablePrice(
        stablecoin=stablecoin,
        sigma=AGGREGATOR_SIGMA,
        admin="",
    )
    for pool in stableswaps:
        _aggregator.add_price_pair(pool)
    return _aggregator


def _create_pegkeepers(factory, aggregator, stableswaps):
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


def _create_factory(stablecoin) -> ControllerFactory:
    return ControllerFactory(
        stablecoin=stablecoin,
        fee_receiver=FEE_RECEIVER_DEFAULT,
    )


def _create_monetary_policy(aggregator, pegkeepers, factory):
    return MonetaryPolicy(
        price_oracle_contract=aggregator,
        controller_factory_contract=factory,
        peg_keepers=pegkeepers,
        rate0=POLICY_RATE0,
        sigma=POLICY_SIGMA,
        target_debt_fraction=POLICY_DEBT_FRACTION,
    )


def create_amm():
    price_oracle = _create_price_oracle()
    stablecoin = _create_stablecoin()
    collateral = _create_collteral()
    amm = LLAMMAPool(
        A=LLAMMA_A,
        BASE_PRICE=INIT_PRICE,
        fee=LLAMMA_FEE,
        admin_fee=LLAMMA_ADMIN_FEE,
        price_oracle_contract=price_oracle,
        collateral=collateral,
        borrowed_token=stablecoin,
    )
    return amm, price_oracle


def _create_tricrypto():
    tricrypto = []
    for coins in TRICRYPTO_COINS:
        tpool = SimCurveCryptoPool(**TRICRYPTO_KWARGS)
        coins = [
            _create_other_stablecoin(symbol) 
            if symbol in STABLE_COINS 
            else _create_collteral(symbol) 
            for symbol in coins
        ]
        tpool.metadata = {
            "coins": {
                "addresses": [c.address for c in coins]
            }
        }  # for `coin_addresses`
        tricrypto.append(tpool)
    return tricrypto


def create_crypto_with_stable_price_oracle(market="weth"):
    stablecoin = _create_stablecoin()
    other_coins = _create_other_coins(CRYPTO_WITH_STABLE_PRICE_COINS)
    factory = _create_factory(stablecoin)
    stableswaps = _create_stableswaps(stablecoin, other_coins, sim=True)
    aggregator = _create_aggregator(stablecoin, stableswaps)
    tricrypto = _create_tricrypto()
    ix = CRYPTO_WITH_STABLE_PRICE_IX[market]
    return CryptoWithStablePrice(
        tricrypto=tricrypto,
        ix=ix,
        stableswap=stableswaps,
        stable_aggregator=aggregator,
        factory=factory,
    )


def create_controller_amm():
    stablecoin = _create_stablecoin()
    other_coins = _create_other_coins()
    factory = _create_factory(stablecoin)
    collateral = _create_collteral()
    price_oracle = _create_price_oracle()
    stableswaps = _create_stableswaps(stablecoin, other_coins)
    aggregator = _create_aggregator(stablecoin, stableswaps)
    pegkeepers = _create_pegkeepers(factory, aggregator, stableswaps)
    monetary_policy = _create_monetary_policy(aggregator, pegkeepers, factory)
    controller, market_amm = factory.add_market(
        token=collateral,
        A=LLAMMA_A,
        fee=LLAMMA_FEE,
        admin_fee=LLAMMA_ADMIN_FEE,
        _price_oracle_contract=price_oracle,
        monetary_policy=monetary_policy,
        loan_discount=MARKET_LOAN_DISCOUNT,
        liquidation_discount=MARKET_LIQUIDATION_DISCOUNT,
        debt_ceiling=MARKET_DEBT_CEILING,
    )
    return controller, market_amm


@pytest.fixture(scope="module")
def accounts():
    return ["user_address_%d" % i for i in range(5)]


@pytest.fixture(scope="module")
def stablecoin(accounts):
    return _create_stablecoin()


@pytest.fixture(scope="module")
def collateral():
    return _create_collteral()


@pytest.fixture(scope="module")
def price_oracle():
    return _create_price_oracle()


@pytest.fixture(scope="module")
def other_coins():
    return _create_other_coins()


@pytest.fixture(scope="module")
def stableswaps(stablecoin, other_coins):
    return _create_stableswaps(stablecoin, other_coins)


@pytest.fixture(scope="module")
def aggregator(stablecoin, stableswaps):
    return _create_aggregator(stablecoin, stableswaps)


@pytest.fixture(scope="module")
def pegkeepers(factory, aggregator, stableswaps):
    return _create_pegkeepers(factory, aggregator, stableswaps)


@pytest.fixture(scope="module")
def factory(stablecoin) -> ControllerFactory:
    return _create_factory(stablecoin)


@pytest.fixture(scope="module")
def monetary_policy(price_oracle, pegkeepers, factory):
    return _create_monetary_policy(price_oracle, pegkeepers, factory)


@pytest.fixture(scope="module")
def controller_and_amm():
    return create_controller_amm()


@pytest.fixture(scope="module")
def crypto_with_stable_price_oracle(market="weth"):
    return create_crypto_with_stable_price_oracle(market)


@pytest.fixture(scope="module")
def tricrypto():
    return _create_tricrypto()
