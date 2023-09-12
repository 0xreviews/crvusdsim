from datetime import datetime, timezone

from curvesim.network.subgraph import query
from curvesim.exceptions import SubgraphResultError
from curvesim.network.utils import sync
from curvesim.logging import get_logger
from curvesim.overrides import override_subgraph_data

from eth_utils import to_checksum_address

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


async def _market_snapshot(llamma_address, end_ts=None):
    if not end_ts:
        end_date = datetime.now(timezone.utc)
        end_ts = int(end_date.timestamp())

    # pylint: disable=consider-using-f-string
    q = """
        query MarketSnapshots {
            snapshots(
                orderBy: timestamp,
                orderDirection: desc,
                first: 1,
                where: {
                    llamma: "%s"
                    timestamp_lte: %d
                    bandSnapshot: true
                }
            ) {
                id
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

                bandSnapshot
                bands (
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
                
                blockNumber
                timestamp

            }
        }
    """ % (
        llamma_address.lower(),
        end_ts,
    )

    r = await convex_crvusd(q)
    try:
        r = r["snapshots"][0]
    except IndexError as e:
        raise SubgraphResultError(
            f"No daily snapshot for this pool: {llamma_address}"
        ) from e

    return r


async def market_snapshot(llamma_address, end_ts=None):
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
    r = await _market_snapshot(llamma_address, end_ts)
    logger.debug("Market snapshot: %s", r)

    # Flatten
    pool = r.pop("market")
    r.update(pool)


    # Coins
    names = ["crvUSD", r["collateralName"]]
    addrs = ["0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E", to_checksum_address(r["collateral"])]
    decimals = [18, int(r["collateralPrecision"])]

    coins = {"names": names, "addresses": addrs, "decimals": decimals}


    # Output
    data = {
        "params": {
            "A": r["A"],
            "rate": r["rate"],
            "future_rate": r["futureRate"],
            "liquidation_discount": r["liquidationDiscount"],
            "loan_discount": r["loanDiscount"],
            "fee": r["fee"],
            "admin_fee": r["adminFee"],
            "BASE_PRICE": r["basePrice"],
            "active_band": r["activeBand"],
            "n_loans": r["nLoans"],
            "min_band": r["minBand"],
            "max_band": r["maxBand"],
            "oracle_price": r["oraclePrice"],
            "collateral_address": r["collateral"],
            "collateral_precision": r["collateralPrecision"],
            "collateral_name": r["collateralName"],
        },
        "symbol": "Curve.fi Stablecoin %s" % (r["collateralName"]),
        "minted": r["minted"],
        "redeemed": r["redeemed"],
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
        "index": r["index"],
        "controller": r["controller"],
        "amm": r["amm"],
        "monetaryPolicy": r["monetaryPolicy"],
        "coins": coins,
    }

    return data


symbol_address_sync = sync(symbol_address)
market_snapshot_sync = sync(market_snapshot)
