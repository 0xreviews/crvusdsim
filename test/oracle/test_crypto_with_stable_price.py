from hypothesis import given
from hypothesis import strategies as st
from ..utils import trade
from ..conftest import (
    create_crypto_with_stable_price_oracle,
    CRYPTO_WITH_STABLE_PRICE_N,
    CRYPTO_WITH_STABLE_PRICE_COLLAT_IX,
)

@given(
    frac=st.floats(min_value=0.1, max_value=0.9),
    i=st.integers(min_value=0, max_value=CRYPTO_WITH_STABLE_PRICE_N - 1),
    market=st.sampled_from(["weth", "wbtc"]),
)
def test_price_change_stableswap(frac, i, market):
    oracle = create_crypto_with_stable_price_oracle(market)
    price1 = oracle.price_w()

    # Lower crvUSD price
    price2 = trade(oracle, oracle.stableswap[i], 1, 0, frac)
    assert price2 > price1

    # Raise crvUSD price
    price3 = trade(oracle, oracle.stableswap[i], 0, 1, frac)
    assert price3 < price2


@given(
    frac=st.floats(min_value=0.1, max_value=0.9),
    i=st.integers(min_value=0, max_value=CRYPTO_WITH_STABLE_PRICE_N - 1),
    market=st.sampled_from(["weth", "wbtc"]),
)
def test_price_change_tricrypto(frac, i, market):
    oracle = create_crypto_with_stable_price_oracle(market)
    price1 = oracle.price_w()

    ix = CRYPTO_WITH_STABLE_PRICE_COLLAT_IX[market][i]

    # Lower collateral price
    price2 = trade(oracle, oracle.tricrypto[i], ix, 0, frac)
    assert price2 < price1

    # Raise collateral price
    price3 = trade(oracle, oracle.tricrypto[i], 0, ix, frac)
    assert price3 > price2
