import os
import pandas as pd

from curvesim.price_data import get

crvUSD_address = "0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E".lower()
wstETH_address = "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0".lower()

def download_prices_data(collateral_address, days=60, data_dir="data"):
    addresses = [collateral_address, crvUSD_address]
    filename = f"{addresses[0].lower()}-{addresses[1].lower()}.csv"
    filepath = os.path.join(data_dir, filename)

    try:
        curr_file = pd.read_csv(filepath, index_col=0)
        curr_file.index = pd.to_datetime(curr_file.index)

    except Exception:
        curr_file = None

    prices, volumes, _ = get(
        addresses,
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
    download_prices_data(wstETH_address)