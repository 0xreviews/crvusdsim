import pytest
import json
from crvusdsim.pool import SimLLAMMAPool, get_sim_market
from curvesim.price_data import get

crvUSD_address = "0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E".lower()
wstETH_address = "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0".lower()
wstETH_llamma_address = "0x37417b2238aa52d0dd2d6252d989e728e8f706e4"
meta_data_dir = "data/pool_metadata_%s.json" % (wstETH_llamma_address)

def create_sim_pool():
    with open(meta_data_dir) as openfile:
        pool_metadata = json.load(openfile)
    
    (
        pool,
        controller,
        stablecoin,
        collateral_token,
        stablecoin,
        aggregator,
        peg_keepers,
        policy,
        factory,
    ) = get_sim_market(pool_metadata)

    return pool

@pytest.fixture(scope="module")
def local_prices():
    addresses = [wstETH_address, crvUSD_address]
    prices, volumes, _ = get(
        addresses,
        chain="mainnet",
        data_dir="data",
        src="local",
    )
    return prices, volumes