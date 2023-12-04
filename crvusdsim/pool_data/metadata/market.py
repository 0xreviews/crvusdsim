from collections import defaultdict
from curvesim.logging import get_logger
from curvesim.pool_data.metadata.base import PoolMetaDataBase
from crvusdsim.pool.crvusd.LLAMMA import UserShares
from crvusdsim.pool.crvusd.controller import Loan

from crvusdsim.pool.crvusd.price_oracle import PriceOracle
from crvusdsim.pool.crvusd.stablecoin import StableCoin
from crvusdsim.pool.crvusd.utils import ERC20

logger = get_logger(__name__)


class MarketMetaData(PoolMetaDataBase):
    """Specific implementation of the `PoolMetaDataInterface` for LLAMMA."""

    def init_kwargs(self, bands_data=None):
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


        pool_kwargs = {
            "address": data["llamma_params"]["address"],
            "A": int(data["llamma_params"]["A"]),
            "rate": int(data["llamma_params"]["rate"]),
            "rate_mul": int(data["llamma_params"]["rate_mul"]),
            "fee": format_float_to_uint256(data["llamma_params"]["fee"]),
            "admin_fee": format_float_to_uint256(data["llamma_params"]["admin_fee"]),
            "BASE_PRICE": format_float_to_uint256(data["llamma_params"]["BASE_PRICE"]),
            "active_band": int(data["llamma_params"]["active_band"]),
            "min_band": int(data["llamma_params"]["min_band"]),
            "max_band": int(data["llamma_params"]["max_band"]),
            "collateral": collateral_token,
            "price_oracle_contract": price_oracle_contract,
        }

        controller_kwargs = {
            "address": data["controller_params"]["address"],
            "loan_discount": format_float_to_uint256(
                data["controller_params"]["loan_discount"]
            ),
            "liquidation_discount": format_float_to_uint256(
                data["controller_params"]["liquidation_discount"]
            ),
            # "n_loans": int(data["controller_params"]["n_loans"]),
            # "rate": format_float_to_uint256(data["controller_params"]["rate"]),
            # "future_rate": format_float_to_uint256(
            #     data["controller_params"]["future_rate"]
            # ),
        }

        if bands_data:
            # convert key from str to int
            bands_x = defaultdict(int)
            bands_y = defaultdict(int)

            for b in data["llamma_params"]["bands_x"]:
                bands_x[int(b)] = int(data["llamma_params"]["bands_x"][b])
            for b in data["llamma_params"]["bands_y"]:
                bands_y[int(b)] = int(data["llamma_params"]["bands_y"][b])

            pool_kwargs["bands_x"] = bands_x
            pool_kwargs["bands_y"] = bands_y

            if bands_data == "controller":
                rate_mul = int(data["llamma_params"]["rate_mul"])
                total_shares = defaultdict(int)
                user_shares = defaultdict(_default_user_shares)
                loan = defaultdict(Loan)
                liquidation_discounts = defaultdict(int)
                total_debt = Loan()
                total_debt.rate_mul = rate_mul
                loans = defaultdict(str)
                loan_ix = defaultdict(int)
                n_loans = 0

                userStates = self._dict["userStates"]

                # need float rate_mul to prevent small positions
                # from being floored to zero when setting init_debt.
                rate_mul_float = rate_mul / 10**18

                for i in range(len(userStates)):
                    _u = userStates[i]
                    user_address = _u["user"]["id"]

                    n1 = int(_u["n1"])
                    n2 = int(_u["n2"])
                    N = n2 - n1 + 1
                    ticks = []

                    # User and band snapshots are taken at different times
                    # so it is possible that a user has shares in a band
                    # but the band is empty. In this case, skip the user.
                    broken_user = False
                    for b_i in range(n1, n2 + 1):
                        if bands_x[b_i] == 0 and bands_y[b_i] == 0:
                            logger.warning(
                                "User %s has shares in band %d but band is empty. Skipping user...", 
                                user_address, 
                                b_i
                            )
                            broken_user = True
                            break
                    if broken_user:
                        continue

                    # As in Vyper code, user shares reflect their deposited
                    # collateral in a band.
                    for b_i in range(n1, n2 + 1):
                        deposited_collateral = format_float_to_uint256(_u["depositedCollateral"]) // N
                        total_shares[b_i] += deposited_collateral
                        ticks.append(deposited_collateral)

                    user_shares[user_address] = UserShares(n1,n2,ticks)

                    init_debt = int(format_float_to_uint256(float(_u["debt"]) / rate_mul_float))
                    init_collateral = format_float_to_uint256(_u["depositedCollateral"])

                    # For the convenience of calculation,
                    # consider all Loan initial rate_mul is one.
                    loan[user_address] = Loan(
                        initial_debt=init_debt,
                        rate_mul=10**18,
                        initial_collateral=init_collateral,
                        timestamp=int(_u["timestamp"]),
                    )
                    liquidation_discounts[user_address] = controller_kwargs[
                        "liquidation_discount"
                    ]
                    total_debt.initial_debt += init_debt
                    total_debt.initial_collateral += init_collateral

                    n_loans += 1
                    loans[n_loans] = user_address
                    loan_ix[user_address] = n_loans

                pool_kwargs["total_shares"] = total_shares
                pool_kwargs["user_shares"] = user_shares

                controller_kwargs["loan"] = loan
                controller_kwargs["loans"] = loans
                controller_kwargs["loan_ix"] = loan_ix
                controller_kwargs["total_debt"] = total_debt
                controller_kwargs["minted"] = format_float_to_uint256(
                    data["controller_params"]["minted"]
                )
                controller_kwargs["redeemed"] = format_float_to_uint256(
                    data["controller_params"]["redeemed"]
                )

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


def _default_user_shares():
    return UserShares()
