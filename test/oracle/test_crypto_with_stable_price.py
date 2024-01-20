import random
from hypothesis import given
from hypothesis import strategies as st
from ..utils import increment_timestamps
from ..conftest import create_crypto_with_stable_price_oracle
from test.utils import approx

def trade(oracle, pool, i, j, frac):
    amount = pool.get_max_trade_size(i, j, frac)
    pool.exchange(i, j, amount)  # sell crvUSD for stablecoin

    objects = oracle.tricrypto + [oracle, oracle.stable_aggregator]

    if hasattr(oracle, "stableswap"):
        objects += oracle.stableswap

    ts = oracle._block_timestamp + 60 * 60
    increment_timestamps(objects, ts)

    return oracle.price_w()

@given(
    frac=st.floats(min_value=0.1, max_value=0.9),
    market=st.sampled_from(["weth", "wbtc", "wsteth", "sfrxeth"]),
)
def test_price_change_stableswap(frac, market):
    oracle = create_crypto_with_stable_price_oracle(market)
    price1 = oracle.price_w()

    i = random.randint(0, len(oracle.stableswap) - 1)

    # Lower crvUSD price
    price2 = trade(oracle, oracle.stableswap[i], 1, 0, frac)
    assert price2 > price1

    # Raise crvUSD price
    price3 = trade(oracle, oracle.stableswap[i], 0, 1, frac)
    assert price3 < price2


@given(
    frac=st.floats(min_value=0.1, max_value=0.9),
    market=st.sampled_from(["weth", "wbtc", "wsteth", "sfrxeth", "tbtc"]),
)
def test_price_change_tricrypto(frac, market):
    oracle = create_crypto_with_stable_price_oracle(market)
    price1 = oracle.price_w()

    i = random.randint(0, len(oracle.tricrypto) - 1)
    ix = oracle.tricrypto_ix[i] + 1

    # Lower collateral price
    price2 = trade(oracle, oracle.tricrypto[i], ix, 0, frac)
    assert price2 < price1

    # Raise collateral price
    price3 = trade(oracle, oracle.tricrypto[i], 0, ix, frac)
    assert price3 > price2

@given(
    frac=st.floats(min_value=0.1, max_value=0.9),
    market=st.sampled_from(["weth", "wbtc", "wsteth", "sfrxeth"]),
)
def test_chainlink_limits(frac, market):
    oracle = create_crypto_with_stable_price_oracle(market)

    price1 = oracle.price_w()

    oracle.set_chainlink(price1, 18, 1)  # tiny bounds

    i = random.randint(0, len(oracle.tricrypto) - 1)
    ix = oracle.tricrypto_ix[i] + 1

    # Lower collateral price, ensure chainlink limits are respected
    price2 = trade(oracle, oracle.tricrypto[i], ix, 0, frac)
    assert approx(price2, price1, 1e-8)

    # Raise collateral price, ensure chainlink limits are respected
    price3 = trade(oracle, oracle.tricrypto[i], 0, ix, frac)
    assert approx(price3, price1, 1e-8)
