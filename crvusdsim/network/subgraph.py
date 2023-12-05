from collections import defaultdict
from datetime import datetime, timezone
from string import Template

from curvesim.network.subgraph import query, _pool_snapshot
from curvesim.exceptions import SubgraphResultError
from curvesim.network.utils import sync
from curvesim.logging import get_logger
from curvesim.overrides import override_subgraph_data

from eth_utils import to_checksum_address

from crvusdsim.pool.crvusd.stablecoin import StableCoin

from ..pool.crvusd.conf import MONETARY_POLICY_CONF, STABLECOIN_TOKEN_CONF


CONVEX_CRVUSD_URL = "https://api.thegraph.com/subgraphs/name/convex-community/crvusd"

logger = get_logger(__name__)


async def convex_crvusd(q):
    """
    Async function to query convex community subgraphs

    Parameters
    ----------
    q : str
        A GraphQL query.

    Returns
    -------
    str
        The returned results.
    """
    url = CONVEX_CRVUSD_URL
    r = await query(url, q)
    if "data" not in r:
        err = ""
        if "errors" in r:
            err = r["errors"]
        raise SubgraphResultError(
            f"No data returned from Convex crvUSD: query: {q}\nerror: {err}"
        )
    return r["data"]


async def symbol_address(symbol, index=0):
    """
    Async function to get a crvUSD Market's contract addresses
    from it's collateral symbol.

    Parameters
    ----------
    symbol: str
        The Market's collateral symbol
    index: int
        The Market's index (if there are multiple markets)

    Returns
    -------
    (str, str, str)
        (LLAMMA address, Controller address, MonetaryPolicy address)

    """
    # pylint: disable=consider-using-f-string
    q = """
        query MarketContractsAddress {
            markets(
                where: {
                    collateralName: "%s"
                }
            ) {
                id
                index
                collateral
                collateralPrecision
                collateralName
                controller
                amm {
                    id
                }
                monetaryPolicy {
                    id
                }
            }
        }
    """ % (
        symbol
    )

    data = await convex_crvusd(q)

    if len(data["markets"]) < 1:
        raise SubgraphResultError("No pools found for symbol query.")

    market = data["markets"][index]

    amm_address = to_checksum_address(market["amm"]["id"])
    controller_address = to_checksum_address(market["controller"])
    policy_address = to_checksum_address(market["amm"]["id"])

    return (amm_address, controller_address, policy_address)


async def get_all(template, key, llamma_address, end_ts=None, first=1000):
    """
    Function to ensure we get all results from subgraph
    despite rate limit (which is at most 1000 results). We assume
    that we want all rows to have the same timestamp.
    Parameters
    ----------
    template : str
        A GraphQL query.
    Returns
    -------
    list
        A list of results.
    """
    skip = 0
    res = []
    ts = None
    while True:
        q = Template(template).substitute(
            llamma_address=llamma_address.lower(),
            end_ts=end_ts,
            first=first,
            skip=skip,
        )

        r = await convex_crvusd(q)

        try:
            r = r[key]

            if len(r):
                # Fix timestamp key
                if key == "bands":
                    for i in range(len(r)):
                        r[i]["timestamp"] = r[i]["snapshot"]["timestamp"]
                        del r[i]["snapshot"]

                if not ts:
                    ts = r[0]["timestamp"]

                r = [item for item in r if item["timestamp"] == ts]
                res.extend(r)

                if len(r) < first:
                    break

                skip += first

        except IndexError as e:
            raise SubgraphResultError(
                f"No user snapshot for this pool: {llamma_address}"
            ) from e

    assert len(set([item["timestamp"] for item in res])) == 1

    return res


async def get_band_snapshots(llamma_address, end_ts=None, first=1000):
    """Get all band snapshots for a given pool."""
    if not end_ts:
        end_date = datetime.now(timezone.utc)
        end_ts = int(end_date.timestamp())

    # Using timestamp_gte in query because we can't sort by timestamp :(
    end_ts -= 86400

    # pylint: disable=consider-using-f-string
    template_query = """
        query bandSnapshot {
            bands(
                first: $first,
                skip: $skip,
                where: {
                    snapshot_: {
                        llamma: "$llamma_address"
                        timestamp_gte: $end_ts
                    }
                }
            ) {
                id
                index
                stableCoin
                collateral
                collateralUsd
                priceOracleUp
                priceOracleDown
                snapshot {
                    timestamp
                }
            }
        }
    """

    res = await get_all(
        template_query, "bands", llamma_address, end_ts=end_ts, first=first
    )
    return res


async def get_user_snapshots(llamma_address, end_ts=None, first=1000):
    """Get all user state snapshots for a given pool."""
    if not end_ts:
        end_date = datetime.now(timezone.utc)
        end_ts = int(end_date.timestamp())

    # pylint: disable=consider-using-f-string
    template_query = """
        query UserSnapshots {
            userStateSnapshots(
                orderBy: timestamp,
                orderDirection: desc,
                first: $first,
                skip: $skip,
                where: {
                    market_: {
                        amm: "$llamma_address"
                    }
                    timestamp_lte: $end_ts
                }
            ) {
                id
                user {
                    id
                }
                collateral
                depositedCollateral
                collateralUp
                loss
                lossPct
                stablecoin
                n
                n1
                n2
                debt
                health
                timestamp
            }
        }
    """

    res = await get_all(
        template_query, "userStateSnapshots", llamma_address, end_ts=end_ts, first=first
    )
    return res


async def get_debt_ceiling(address):
    """
    Async function to get debt ceiling
    from its address.

    Parameters
    ----------
    address: str

    Returns
    -------
    int

    """
    address = address.lower()

    # pylint: disable=consider-using-f-string
    q = """
        query GetDebtCeiling {
            debtCeilings (
                first: 1
                orderBy: blockTimestamp
                orderDirection: desc
                where: {
                    addr: "%s"
                }
            ) {
                id
                addr
                debtCeiling
                blockNumber
                blockTimestamp
            }
        }
    """ % (
        address
    )

    data = await convex_crvusd(q)

    if len(data["debtCeilings"]) < 1:
        raise SubgraphResultError("No debt ceiling found for symbol query.")

    ceiling = int(data["debtCeilings"][0]["debtCeiling"])

    return ceiling


async def _market_snapshot(
    llamma_address, end_ts, use_band_snapshot, use_user_snapshot
):
    if not end_ts:
        end_date = datetime.now(timezone.utc)
        end_ts = int(end_date.timestamp())

    # pylint: disable=consider-using-f-string
    template_query = """
        query MarketSnapshots {
            snapshots(
                orderBy: timestamp,
                orderDirection: desc,
                first: 1,
                where: {
                    llamma: "$llamma_address"
                    timestamp_lte: $end_ts
                    bandSnapshot: false
                    userStateSnapshot: false
                }
            ) {
                id
                A
                rate
                futureRate
                liquidationDiscount
                loanDiscount
                minted
                redeemed
                totalKeeperDebt
                totalCollateral
                totalCollateralUsd
                totalSupply
                available
                totalDebt
                nLoans
                crvUsdAdminFees
                collateralAdminFees
                adminBorrowingFees
                fee
                adminFee
                ammPrice
                oraclePrice
                basePrice
                activeBand
                minBand
                maxBand
                blockNumber
                timestamp

                market {
                    id
                    index
                    collateral
                    collateralPrecision
                    collateralName
                    controller
                    amm {
                        id
                    }
                    monetaryPolicy {
                        id
                    }
                }

                policy {
                    id
                    priceOracle
                    keepers
                    pegKeepers(first: 5) {
                        pegKeeper {
                            id
                            active
                            pool
                            debt
                            totalProvided
                            totalWithdrawn
                            totalProfit
                        }
                    }
                    benchmarkRates(first: 1, orderBy: blockTimestamp, orderDirection: desc) {
                        id
                        rate
                        blockNumber
                        blockTimestamp
                    }
                    debtFractions(first: 1, orderBy: blockTimestamp, orderDirection: desc) {
                        id
                        target
                        blockNumber
                        blockTimestamp
                    }
                    
                }

                bandSnapshot
                bands (
                    first: 1000,
                    orderBy: index
                    orderDirection: asc
                ) {
                    id
                    index
                    stableCoin
                    collateral
                    collateralUsd
                    priceOracleUp
                    priceOracleDown
                }

                userStateSnapshot
                userStates(
                    first: 1000,
                    orderBy: depositedCollateral
                    orderDirection: desc
                ) {
                    id
                    user {
                        id
                    }
                    collateral
                    depositedCollateral
                    collateralUp
                    loss
                    lossPct
                    stablecoin
                    n
                    n1
                    n2
                    debt
                    health
                    timestamp
                }

            }
            llammaRates(
                orderBy: blockTimestamp,
                orderDirection: desc,
                first: 1,
                where: {
                    llamma: "$llamma_address"
                    blockTimestamp_lte: $end_ts
                }
            ) {
                id
                llamma {
                    id
                }
                rate
                rateMul
                blockTimestamp
            }
        }
    """

    q = Template(template_query).substitute(
        llamma_address=llamma_address.lower(),
        end_ts=end_ts,
    )

    r = await convex_crvusd(q)

    try:
        res = r["snapshots"][0]
        res["llammaRate"] = r["llammaRates"][0]

        if use_user_snapshot:
            user_data = await get_user_snapshots(llamma_address, end_ts=end_ts)
            logger.debug("User snapshot: %s", user_data)
            res["userStateSnapshot"] = True
            res["userStates"] = user_data

        if use_band_snapshot:
            band_data = await get_band_snapshots(llamma_address, end_ts=end_ts)
            logger.debug("Bands snapshot: %s", band_data)
            res["bandSnapshot"] = True
            res["bands"] = band_data

    except IndexError as e:
        raise SubgraphResultError(
            f"No daily snapshot for this pool: {llamma_address}"
        ) from e

    return res


async def _stableswap_snapshot(pool_addresses, chain = "mainnet"):
    pools_params = []
    for addr in pool_addresses:
        r = await _pool_snapshot(address=addr, chain=chain, env="prod")
        coins = []
        for i in range(len(r["pool"]["coins"])):
            coins.append(
                {
                    "address": r["pool"]["coins"][i],
                    "name": r["pool"]["coinNames"][i],
                    "symbol": r["pool"]["coinNames"][i],
                    "decimals": int(r["pool"]["coinDecimals"][i]),
                }
            )

        pools_params.append(
            {
                "address": r["pool"]["address"],
                "A": int(r["A"]),
                "D": [int(reserve) for reserve in r["reserves"]],
                "n": len(r["pool"]["coins"]),
                "rates": [
                    10 ** (36 - int(decimals)) for decimals in r["pool"]["coinDecimals"]
                ],
                "fee": int(float(r["fee"]) * 1e10),
                "admin_fee": int(float(r["adminFee"]) * 1e10),
                "name": r["pool"]["name"],
                "symbol": r["pool"]["symbol"],
                "decimals": 18,
                "coins": coins,
                "chain": chain,
            }
        )
    return pools_params


async def market_snapshot(
    llamma_address, end_ts=None, use_band_snapshot=False, use_user_snapshot=False
):
    """
    Async function to pull Market state and metadata from daily snapshots.

    Parameters
    ----------
    llamma_address : str
        The Market's LLAMMA address.

    Returns
    -------
    dict
        A formatted dict of Market state/metadata information.

    """
    r = await _market_snapshot(
        llamma_address, end_ts, use_band_snapshot, use_user_snapshot
    )
    logger.debug("Market snapshot: %s", r)

    # Coins
    names = [
        STABLECOIN_TOKEN_CONF["symbol"],
        r["market"]["collateralName"],
    ]
    addrs = [
        STABLECOIN_TOKEN_CONF["address"],
        to_checksum_address(r["market"]["collateral"]),
    ]
    decimals = [18, int(r["market"]["collateralPrecision"])]

    coins = {"names": names, "addresses": addrs, "decimals": decimals}

    bands_x = defaultdict(int)
    bands_y = defaultdict(int)
    for b in r["bands"]:
        bands_x[int(b["index"])] = int(float(b["stableCoin"]) * 1e18)
        bands_y[int(b["index"])] = int(float(b["collateral"]) * 1e18)

    # peg_keepers_params
    peg_keepers_params = [
        {
            "address": pk["pegKeeper"]["id"],
            "active": pk["pegKeeper"]["active"],
            "pool": pk["pegKeeper"]["pool"],
            "debt": pk["pegKeeper"]["debt"],
            "total_provided": pk["pegKeeper"]["totalProvided"],
            "total_withdrawn": pk["pegKeeper"]["totalWithdrawn"],
            "total_profit": pk["pegKeeper"]["totalProfit"],
        }
        for pk in r["policy"]["pegKeepers"]
    ]

    # stableswap pools
    stableswap_pools_params = await _stableswap_snapshot(
        [p["pool"] for p in peg_keepers_params]
    )

    # Output
    data = {
        "llamma_params": {
            "name": "Curve.fi Stablecoin %s" % (r["market"]["collateralName"]),
            "address": r["market"]["amm"]["id"],
            "A": r["A"],
            "rate": r["llammaRate"]["rate"],
            "rate_mul": r["llammaRate"]["rateMul"],
            "fee": r["fee"],
            "admin_fee": r["adminFee"],
            "BASE_PRICE": r["basePrice"],
            "active_band": r["activeBand"],
            "min_band": r["minBand"],
            "max_band": r["maxBand"],
            "oracle_price": r["oraclePrice"],
            "collateral_address": r["market"]["collateral"],
            "collateral_precision": r["market"]["collateralPrecision"],
            "collateral_name": r["market"]["collateralName"],
            "collateral_symbol": r["market"]["collateralName"],
            "bands_x": bands_x,
            "bands_y": bands_y,
        },
        "controller_params": {
            "address": r["market"]["controller"],
            "liquidation_discount": r["liquidationDiscount"],
            "loan_discount": r["loanDiscount"],
            "rate": r["rate"],
            "minted": r["minted"],
            "redeemed": r["redeemed"],
            "future_rate": r["futureRate"],
            "n_loans": r["nLoans"],
        },
        "collateral_token_params": {
            "address": r["market"]["collateral"],
            "name": r["market"]["collateralName"],
            "symbol": r["market"]["collateralName"],
            "precision": r["market"]["collateralPrecision"],
        },
        "policy_params": {
            "address": r["policy"]["id"],
            "rate0": int(r["policy"]["benchmarkRates"][0]["rate"])
            if len(r["policy"]["benchmarkRates"]) > 0
            else MONETARY_POLICY_CONF["rate0"],
            "sigma": MONETARY_POLICY_CONF["sigma"],  # @todo subgraph not supports
            "fraction": int(r["policy"]["debtFractions"][0]["target"])
            if len(r["policy"]["debtFractions"]) > 0
            else MONETARY_POLICY_CONF["fraction"],
        },
        "stableswap_pools_params": stableswap_pools_params,
        "peg_keepers_params": peg_keepers_params,
        "price_oracle_params": {
            "oracle_price": r["oraclePrice"],
        },
        "name": "Curve.fi Stablecoin %s" % (r["market"]["collateralName"]),
        "symbol": "Curve.fi Stablecoin %s" % (r["market"]["collateralName"]),
        "totalKeeperDebt": r["totalKeeperDebt"],
        "totalCollateral": r["totalCollateral"],
        "totalSupply": r["totalSupply"],
        "available": r["available"],
        "totalDebt": r["totalDebt"],
        "crvUsdAdminFees": r["crvUsdAdminFees"],
        "collateralAdminFees": r["collateralAdminFees"],
        "adminBorrowingFees": r["adminBorrowingFees"],
        "ammPrice": r["ammPrice"],
        "bandSnapshot": r["bandSnapshot"],
        "bands": r["bands"],
        "userStateSnapshot": r["userStateSnapshot"],
        "userStates": r["userStates"],
        "blockNumber": r["blockNumber"],
        "timestamp": r["timestamp"],
        "index": r["market"]["index"],
        "coins": coins,
    }

    return data


symbol_address_sync = sync(symbol_address)
market_snapshot_sync = sync(market_snapshot)
debt_ceiling_sync = sync(get_debt_ceiling)
