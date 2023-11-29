from datetime import datetime
import os
from time import mktime
import pandas as pd

from curvesim.price_data import get

crvUSD_address = "0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E".lower()
wstETH_address = "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0".lower()
USDT_address = "0xdAC17F958D2ee523a2206206994597C13D831ec7".lower()
USDC_address = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48".lower()
TUSD_address = "0x0000000000085d4780B73119b644AE5ecd22b376".lower()
USDP_address = "0x8E870D67F660D95d5be530380D0eC0bd388289E1".lower()


def download_prices_data(token_address, days=60, data_dir="data"):
    filename = f"{token_address.lower()}-{crvUSD_address.lower()}.csv"
    filepath = os.path.join(data_dir, filename)

    try:
        curr_file = pd.read_csv(filepath, index_col=0)
        curr_file.index = pd.to_datetime(curr_file.index)

    except Exception:
        curr_file = None

    prices, volumes, _ = get(
        [token_address, crvUSD_address],
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
    download_prices_data(wstETH_address, days=60)
    download_prices_data(USDT_address, days=60)
    download_prices_data(USDC_address, days=60)
    download_prices_data(TUSD_address, days=60)
    download_prices_data(USDP_address, days=60)