from collections import defaultdict
from curvesim.logging import get_logger
from curvesim.pool_data.metadata.base import PoolMetaDataBase

from crvusdsim.pool.crvusd.price_oracle import PriceOracle
from crvusdsim.pool.crvusd.stablecoin import StableCoin
from crvusdsim.pool.crvusd.utils import ERC20

logger = get_logger(__name__)


class MarketMetaData(PoolMetaDataBase):
    """Specific implementation of the `PoolMetaDataInterface` for LLAMMA."""

    def init_kwargs(self, bands=False):
        data = self._dict

        collateral_token = ERC20(
            address=data["collateral_token_params"]["address"],
            decimals=int(data["collateral_token_params"]["precision"]),
            symbol=data["collateral_token_params"]["symbol"],
            name=data["collateral_token_params"]["name"],
        )

        monetary_policy_kwargs = {
            "address": data["policy_params"]["address"],
            "rate0": data["policy_params"]["rate0"],
            "sigma": data["policy_params"]["sigma"],
            "fraction": data["policy_params"]["fraction"],
        }

        price_oracle_contract = PriceOracle(
            format_float_to_uint256(data["price_oracle_params"]["oracle_price"])
        )

        stableswap_pools_kwargs = data["stableswap_pools_params"]
        
        peg_keepers_kwargs = data["peg_keepers_params"]

        # convert key from str to int
        bands_x = {}
        bands_y = {}
        for b in data["llamma_params"]["bands_x"]:
            bands_x[int(b)] = int(data["llamma_params"]["bands_x"][b])
        for b in data["llamma_params"]["bands_y"]:
            bands_y[int(b)] = int(data["llamma_params"]["bands_y"][b])

        pool_kwargs = {
            "address": data["llamma_params"]["address"],
            "A": int(data["llamma_params"]["A"]),
            "fee": format_float_to_uint256(data["llamma_params"]["fee"]),
            "admin_fee": format_float_to_uint256(data["llamma_params"]["admin_fee"]),
            "BASE_PRICE": format_float_to_uint256(data["llamma_params"]["BASE_PRICE"]),
            "active_band": int(data["llamma_params"]["active_band"]),
            "min_band": int(data["llamma_params"]["min_band"]),
            "max_band": int(data["llamma_params"]["max_band"]),
            "collateral": collateral_token,
            "price_oracle_contract": price_oracle_contract,
            "bands_x": bands_x,
            "bands_y": bands_y,
        }

        controller_kwargs = {
            "address": data["controller_params"]["address"],
            "loan_discount": format_float_to_uint256(
                data["controller_params"]["loan_discount"]
            ),
            "liquidation_discount": format_float_to_uint256(
                data["controller_params"]["liquidation_discount"]
            ),
            "n_loans": int(data["controller_params"]["n_loans"]),
            # "rate": format_float_to_uint256(data["controller_params"]["rate"]),
            # "future_rate": format_float_to_uint256(
            #     data["controller_params"]["future_rate"]
            # ),
        }

        if bands:
            bands_x = defaultdict(int)
            bands_y = defaultdict(int)
            bands = self._dict["bands"]
            for i in range(len(bands)):
                _b = bands[i]
                bands_x[int(_b["index"])] = int(float(_b["stableCoin"]) * 10**18)
                bands_y[int(_b["index"])] = int(float(_b["collateral"]) * 10**18)
            pool_kwargs["bands_x"] = bands_x
            pool_kwargs["bands_y"] = bands_y

        return (
            pool_kwargs,
            controller_kwargs,
            monetary_policy_kwargs,
            stableswap_pools_kwargs,
            peg_keepers_kwargs,
        )

    @property
    def coins(self):
        return self._dict["coins"]["addresses"]

    @property
    def coin_names(self):
        return self._dict["coins"]["names"]

    @property
    def n(self):
        return len(self._dict["coins"]["names"])


def format_float_to_uint256(n: str, decimals=18) -> int:
    return int(float(n) * 10**decimals)
