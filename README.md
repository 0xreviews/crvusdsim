# crvUSDsim

crvUSDsim is a tool simulating Curve Stablecoin.

## Features

- Simulate interactions with crvUSD pools in Python
- Analyze the effects of parameter changes on pool performance
- Develop custom simulation tools for parameter optimization
- Simulate the anti-risk ability of the protocol in extreme cases

## Quick Start

- install with [poetry](https://python-poetry.org/)

```bash
poetry install
```

- run `Hello World`

```shell
>>> poetry run python -m crvusdsim
[INFO][11:29:54][crvusdsim.pipelines.simple]-92751: Simulating mode: rate
[INFO][11:29:57][curvesim.price_data.sources]-92751: Fetching CoinGecko price data...
[INFO][11:30:08][curvesim.price_data.sources]-92751: Fetching CoinGecko price data...
[INFO][11:30:08][curvesim.price_data.sources]-92751: Fetching CoinGecko price data...
[INFO][11:30:08][curvesim.price_data.sources]-92751: Fetching CoinGecko price data...
[INFO][11:30:09][curvesim.price_data.sources]-92751: Fetching CoinGecko price data...
[INFO][11:30:16][crvusdsim.templates.Strategy]-92883: [Curve.fi Stablecoin wstETH] Simulating with {'rate0': 0.15}
[INFO][11:30:16][crvusdsim.templates.Strategy]-92880: [Curve.fi Stablecoin wstETH] Simulating with {'rate0': 0.1}
[INFO][11:30:16][crvusdsim.templates.Strategy]-92877: [Curve.fi Stablecoin wstETH] Simulating with {'rate0': 0.05}
Elapsed time: 28.6576099395752
```

## Documentation

Check out the full documentation at <https://crvusdsim.readthedocs.io/>. We recommend starting with the "Quickstart" guide.

## Basic Use: Autosim

The `autosim()` function simulates existing Curve Stablecoin Market with range of parameters (such like rate0, A, loan_discount). The function fetches pool properties (e.g., current pool size) and 2 months of price/volume data, runs multiple simulations in parallel, and returns a results object that can be introspected or generate charts.

crvUSDsim supported by the [Convex Community Subgraphs/crvusd](https://thegraph.com/hosted-service/subgraph/convex-community/crvusd) can be simulated directly by inputting the LLAMMA pool's address or Collateral's Symbol (e.g. "wstETH").

### Example

Pythonic interaction with Curve Stablecoin market objects (including LLAMMA pool, Controller, Aggregator, PegKeepers, etc.)::

```shell
>>> import crvusdsim

>>> (pool, controller, collateral_token, stablecoin, aggregator, price_oracle, stableswap_pools, peg_keepers, policy, factory)
>>>     = crvusdsim.pool.get(market_name, bands_data="controller")

>>> pool.name
'Curve.fi Stablecoin wstETH'

>>> pool.coin_names
['wstETH', 'crvUSD']
>>> pool.A
100

>>> sum(pool.bands_x.values())
0
>>> sum(pool.bands_y.values())
40106052164494685140992

>>> len(pool.user_shares)
392

>>> dx = 10**18
>>> pool.trade(0, 1, dx) # dx, dy, fees
(1000000000000000000, 445225238462727, 6000000000000000)

>>> controller.loan_discount
90000000000000000

>>> controller.liquidation_discount
60000000000000000

>>> len(controller.loan)
392

>>> user0 = controller.loans[1] # user address
>>> loan0 = controller.loan[user0] # :class:Loan
>>> (loan0.initial_debt, loan0.initial_collateral, loan0.rate_mul, loan0.timestamp)
(9779961749290509154648064, 6785745612366175797248, 1000000000000000000, 1700712599)
```

Rate simulations to see results of varying `rate0` parameters in `MonetaryPolicy`::

```python
>>> import crvusdsim

>>> res = crvusdsim.autosim(pool="wstETH", sim_mode="rate", rate0=[0.05, 0.075, 0.10, 0.125, 0.15])

[INFO][10:02:42][crvusdsim.pipelines.simple]-84886: Simulating mode: rate
[INFO][10:02:50][curvesim.price_data.sources]-84886: Fetching CoinGecko price data...
[INFO][10:03:51][curvesim.price_data.sources]-84886: Fetching CoinGecko price data...
[INFO][10:03:52][curvesim.price_data.sources]-84886: Fetching CoinGecko price data...
[INFO][10:05:44][curvesim.price_data.sources]-84886: Fetching CoinGecko price data...
[INFO][10:07:22][curvesim.price_data.sources]-84886: Fetching CoinGecko price data...
[INFO][10:07:32][crvusdsim.templates.Strategy]-84936: [Curve.fi Stablecoin wstETH] Simulating with {'rate0': 0.05}
[INFO][10:07:32][crvusdsim.templates.Strategy]-84937: [Curve.fi Stablecoin wstETH] Simulating with {'rate0': 0.125}
[INFO][10:07:32][crvusdsim.templates.Strategy]-84935: [Curve.fi Stablecoin wstETH] Simulating with {'rate0': 0.075}
[INFO][10:07:32][crvusdsim.templates.Strategy]-84934: [Curve.fi Stablecoin wstETH] Simulating with {'rate0': 0.1}
[INFO][10:07:33][crvusdsim.templates.Strategy]-84938: [Curve.fi Stablecoin wstETH] Simulating with {'rate0': 0.15}
```

Arbitrage simulations to see results of varying fee and amplification (A) parameters in LLAMMA pool:

```python
>>> res = crvusdsim.autosim(pool="wstETH", sim_mode="pool", A=[50, 60, 80, 100])

[INFO][14:57:58][crvusdsim.pipelines.simple]-82656: Simulating mode: pool
[INFO][14:58:00][curvesim.price_data.sources]-82656: Fetching CoinGecko price data...
[INFO][14:58:05][crvusdsim.templates.Strategy]-82729: [Curve.fi Stablecoin wstETH] Simulating with {'A': 50}
[INFO][14:58:05][crvusdsim.templates.Strategy]-82730: [Curve.fi Stablecoin wstETH] Simulating with {'A': 100}
[INFO][14:58:05][crvusdsim.templates.Strategy]-82731: [Curve.fi Stablecoin wstETH] Simulating with {'A': 60}
[INFO][14:58:05][crvusdsim.templates.Strategy]-82732: [Curve.fi Stablecoin wstETH] Simulating with {'A': 80}
```

Arbitrage simulations to see results of varying loan_discount and liquidation_discount parameters in `Controller`::

```python
>>> loan_discounts = [int(d * 10**18) for d in [0.09, 0.10, 0.11, 0.12]]
>>> res = crvusdsim.autosim(pool="wstETH", sim_mode="controller", loan_discount=loan_discounts, liquidation_discount=[int(0.06 * 10**18)])

[INFO][17:01:13][crvusdsim.pipelines.simple]-91016: Simulating mode: controller
[INFO][17:01:15][curvesim.price_data.sources]-91016: Fetching CoinGecko price data...
[INFO][17:02:56][crvusdsim.templates.Strategy]-91050: [Curve.fi Stablecoin wstETH] Simulating with {'loan_discount': 100000000000000000, 'liquidation_discount': 60000000000000000}
[INFO][17:02:56][crvusdsim.templates.Strategy]-91052: [Curve.fi Stablecoin wstETH] Simulating with {'loan_discount': 110000000000000000, 'liquidation_discount': 60000000000000000}
[INFO][17:02:56][crvusdsim.templates.Strategy]-91049: [Curve.fi Stablecoin wstETH] Simulating with {'loan_discount': 90000000000000000, 'liquidation_discount': 60000000000000000}
[INFO][17:02:56][crvusdsim.templates.Strategy]-91053: [Curve.fi Stablecoin wstETH] Simulating with {'loan_discount': 120000000000000000, 'liquidation_discount': 60000000000000000}
```

Arbitrage simulations to see results of varying N of user's position::

```python
>>> res = crvusdsim.autosim(pool="wstETH", sim_mode="N", N=[4, 6, 8, 10, 20, 40, 50])

[INFO][17:17:50][crvusdsim.pipelines.simple]-91016: Simulating mode: N
[INFO][17:17:53][curvesim.price_data.sources]-91016: Fetching CoinGecko price data...
[INFO][17:17:59][crvusdsim.templates.Strategy]-91351: [Curve.fi Stablecoin wstETH] Simulating with {'N': 8}
[INFO][17:18:01][crvusdsim.templates.Strategy]-91354: [Curve.fi Stablecoin wstETH] Simulating with {'N': 40}
[INFO][17:18:01][crvusdsim.templates.Strategy]-91349: [Curve.fi Stablecoin wstETH] Simulating with {'N': 4}
[INFO][17:18:01][crvusdsim.templates.Strategy]-91355: [Curve.fi Stablecoin wstETH] Simulating with {'N': 50}
[INFO][17:18:01][crvusdsim.templates.Strategy]-91352: [Curve.fi Stablecoin wstETH] Simulating with {'N': 10}
[INFO][17:18:01][crvusdsim.templates.Strategy]-91353: [Curve.fi Stablecoin wstETH] Simulating with {'N': 20}
[INFO][17:18:01][crvusdsim.templates.Strategy]-91350: [Curve.fi Stablecoin wstETH] Simulating with {'N': 6}
```

## Simulation Results

The simulation returns a SimResults object that can plot simulation metrics or return them as DataFrames.

### Plotting results

```python
#Plot results using Altair
res.plot()

#Save plot results as results.html
res.plot(save_as="results.html")
```

### Example output

- `sim_mode="rate"`

![Alt text](/docs/images/rate_plot_summary_screenshot.png?raw=true "Summary statistics(sim_mode='rate')")

![Alt text](/docs/images/rate_plot_timeseries_screenshot.png?raw=true "Timeseries data(sim_mode='rate')")

### Summary statistics

- `sim_mode="rate"`

```python
>>> res.summary()

metric	annualized_rate	users_debt	crvusd_price	agg_price
stat	mean	mean	mean	mean
0	0.044408	1.580274e+06	1.002537	1.002775
1	0.066533	1.583135e+06	1.002537	1.002775
2	0.088607	1.585936e+06	1.002537	1.002775
3	0.110631	1.588681e+06	1.002537	1.002775
4	0.132608	1.591372e+06	1.002537	1.002775


>>> res.summary(full=True)

rate0	annualized_rate mean	users_debt mean	crvusd_price mean	agg_price mean
0	0.050	0.044408	1.580274e+06	1.002537	1.002775
1	0.075	0.066533	1.583135e+06	1.002537	1.002775
2	0.100	0.088607	1.585936e+06	1.002537	1.002775
3	0.125	0.110631	1.588681e+06	1.002537	1.002775
4	0.150	0.132608	1.591372e+06	1.002537	1.002775

>>> res.data()

	run	timestamp	annualized_rate	users_debt	crvusd_price	agg_price
0	0	2023-10-03 23:30:00+00:00	0.046259	1.574365e+06	1.001229	1.001890
1	0	2023-10-03 23:38:34+00:00	0.046259	1.574366e+06	1.001229	1.001890
2	0	2023-10-03 23:47:08+00:00	0.046259	1.574367e+06	1.001229	1.001890
3	0	2023-10-03 23:55:42+00:00	0.046259	1.574368e+06	1.001229	1.001890
4	0	2023-10-04 00:04:17+00:00	0.046259	1.574369e+06	1.001229	1.001890
...	...	...	...	...	...	...
51240	4	2023-12-03 22:55:42+00:00	0.123962	1.607443e+06	1.003847	1.003959
51241	4	2023-12-03 23:04:17+00:00	0.123962	1.607447e+06	1.003847	1.003959
51242	4	2023-12-03 23:12:51+00:00	0.123962	1.607450e+06	1.003847	1.003959
51243	4	2023-12-03 23:21:25+00:00	0.123962	1.607453e+06	1.003847	1.003959
51244	4	2023-12-03 23:30:00+00:00	0.124045	1.607456e+06	1.003847	1.003946

51245 rows × 6 columns

>>> res.data(full=True)

	rate0	run	timestamp	annualized_rate	users_debt	crvusd_price	agg_price
0	0.05	0	2023-10-03 23:30:00+00:00	0.046259	1.574365e+06	1.001229	1.001890
1	0.05	0	2023-10-03 23:38:34+00:00	0.046259	1.574366e+06	1.001229	1.001890
2	0.05	0	2023-10-03 23:47:08+00:00	0.046259	1.574367e+06	1.001229	1.001890
3	0.05	0	2023-10-03 23:55:42+00:00	0.046259	1.574368e+06	1.001229	1.001890
4	0.05	0	2023-10-04 00:04:17+00:00	0.046259	1.574369e+06	1.001229	1.001890
...	...	...	...	...	...	...	...
51240	0.15	4	2023-12-03 22:55:42+00:00	0.123962	1.607443e+06	1.003847	1.003959
51241	0.15	4	2023-12-03 23:04:17+00:00	0.123962	1.607447e+06	1.003847	1.003959
51242	0.15	4	2023-12-03 23:12:51+00:00	0.123962	1.607450e+06	1.003847	1.003959
51243	0.15	4	2023-12-03 23:21:25+00:00	0.123962	1.607453e+06	1.003847	1.003959
51244	0.15	4	2023-12-03 23:30:00+00:00	0.124045	1.607456e+06	1.003847	1.003946
51245 rows × 7 columns
```


## Support

If you are having issues, please let us know. You can reach us via the following

GitHub: crvUSDsim issues <https://github.com/0xreviews/crvusdsim/issues>

## License

Portions of the codebase are authorized derivatives of code owned by Curve.fi (Swiss Stake GmbH). These are the Vyper snippets used for testing and the Python code derived from them (`crvusdsim/pool/crvusd`); there are copyright notices placed appropriately. The rest of the codebase has an MIT license.
