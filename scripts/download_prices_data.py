import os
import pandas as pd

from crvusdsim.pool import get_sim_pool
from curvesim.price_data import get

wstETH_llamma_address = "0x37417b2238aa52d0dd2d6252d989e728e8f706e4"

def download_prices_data(collateral_address, days=60, data_dir="data"):
    pool = get_sim_pool(collateral_address)
    sim_assets = pool.assets
    addresses = sim_assets.addresses
    pair = sim_assets.symbols
    filename = f"{addresses[0]}-{addresses[1]}.csv"
    filepath = os.path.join(data_dir, filename)

    try:
        curr_file = pd.read_csv(filepath, index_col=0)
        curr_file.index = pd.to_datetime(curr_file.index)

    except Exception:
        curr_file = None

    prices, volumes, _ = get(
        sim_assets.addresses,
        chain="mainnet",
        days=days,
        data_dir=data_dir,
        src="coingecko",
    )

    # Create the pandas DataFrame
    df = pd.concat(
        [prices.set_axis(["price"], axis=1), volumes.set_axis(["volume"], axis=1)],
        axis="columns",
    )

    os.makedirs(data_dir, exist_ok=True)
    df.to_csv(filepath)


if __name__ == "__main__":
    download_prices_data(wstETH_llamma_address)