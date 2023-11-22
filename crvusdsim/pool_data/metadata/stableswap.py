from curvesim.pool.stableswap.pool import CurvePool
from curvesim.pool_data.metadata.base import PoolMetaDataBase


class CurveStableSwapPoolMetaData(PoolMetaDataBase):
    """Specific implementation of the `PoolMetaDataInterface` for Stableswap."""

    def init_kwargs(self):
        data = self._dict

        def process_to_kwargs(data):
            kwargs = {

                "A": data["A"],
                "D": data["D"],
                "n": data["n"],
                "rates": data["rates"],
                "fee": data["fee"],
                "admin_fee": data["admin_fee"],
                "address": data["address"],
                "decimals": data["decimals"],
                "name": data["name"],
                "symbol": data["symbol"],
                "coins": data["coins"],
            }
            return kwargs

        kwargs = process_to_kwargs(data)

        return kwargs

    @property
    def coins(self):
        return self._dict["coins"]

    @property
    def coin_names(self):
        return [c.name for c in self._dict["coins"]]
    
    @property
    def coin_addresses(self):
        return [c.address for c in self._dict["coins"]]

    @property
    def n(self):
        return self._dict["n"]
