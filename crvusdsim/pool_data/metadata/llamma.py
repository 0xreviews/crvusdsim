from collections import defaultdict
from curvesim.logging import get_logger
from curvesim.pool_data.metadata.base import PoolMetaDataBase

from ...pool.crvusd.price_oracle.price_oracle import PriceOracle

logger = get_logger(__name__)


class PoolMetaData(PoolMetaDataBase):
    """Specific implementation of the `PoolMetaDataInterface` for LLAMMA."""

    def init_kwargs(self, bands=True, normalize=True):
        data = self._dict

        pool_kwargs = {
            "A": int(data["params"]["A"]),
            "fee": format_float_to_uint256(data["params"]["fee"]),
            "admin_fee": format_float_to_uint256(data["params"]["admin_fee"]),
            "BASE_PRICE": format_float_to_uint256(data["params"]["BASE_PRICE"]),
            "active_band": int(data["params"]["active_band"]),
            "min_band": int(data["params"]["min_band"]),
            "max_band": int(data["params"]["max_band"]),
            "collateral": {
                "address": data["params"]["collateral_address"],
                "precision": int(data["params"]["collateral_precision"]),
            },
            "price_oracle_contract": PriceOracle(
                format_float_to_uint256(data["params"]["oracle_price"])
            ),
        }

        controller_kwargs = {
            "loan_discount": format_float_to_uint256(data["params"]["loan_discount"]),
            "liquidation_discount": format_float_to_uint256(
                data["params"]["liquidation_discount"]
            ),
            "n_loans": int(data["params"]["n_loans"]),
            "rate": format_float_to_uint256(data["params"]["rate"]),
            "future_rate": format_float_to_uint256(data["params"]["future_rate"]),
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

        return pool_kwargs, controller_kwargs

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
