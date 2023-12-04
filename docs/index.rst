.. crvusdsim documentation master file, created by
   sphinx-quickstart on Sun Nov 19 15:10:15 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

crvUSDsim: Python Simulator for Curve Stablecoin
================================================

Release v\ |version|. (:ref:`Installation <install>`)

.. toctree::
   :maxdepth: 2
   :caption: Contents:

--------------------------

Pythonic interaction with Curve Stablecoin market objects (include LLAMMA pool, controller, aggregator, PegKeepers, etc.)::

   >>> import crvusdsim

   >>> (pool, controller, collateral_token, stablecoin, aggregator,  price_oracle, stableswap_pools, peg_keepers, policy, factory) 
   >>>      = crvusdsim.pool.get(market_name, bands_data="controller")

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



Arbitrage simulations to see results of varying fee and amplification (A) parameters in `LLAMMA pool`::

   >>> import crvusdsim
   >>> res = crvusdsim.autosim(pool="wstETH", sim_mode="pool", A=[50, 60, 80, 100])

   [INFO][14:57:58][crvusdsim.pipelines.simple]-82656: Simulating mode: pool
   [INFO][14:58:00][curvesim.price_data.sources]-82656: Fetching CoinGecko price data...
   [INFO][14:58:05][crvusdsim.templates.Strategy]-82729: [Curve.fi Stablecoin wstETH] Simulating with {'A': 50}
   [INFO][14:58:05][crvusdsim.templates.Strategy]-82730: [Curve.fi Stablecoin wstETH] Simulating with {'A': 100}
   [INFO][14:58:05][crvusdsim.templates.Strategy]-82731: [Curve.fi Stablecoin wstETH] Simulating with {'A': 60}
   [INFO][14:58:05][crvusdsim.templates.Strategy]-82732: [Curve.fi Stablecoin wstETH] Simulating with {'A': 80}

   >>> res.summary()
   
   metric	pool_value	arb_profits_percent	pool_volume	arb_profit	pool_fees
   stat	annualized_returns	annualized_arb_profits	sum	sum	sum
   0	0.411643	-0.027450	4.558058e+09	9.609988e+06	6.034716e+07
   1	0.417621	-0.027471	4.510472e+09	9.859186e+06	5.982183e+07
   2	0.415172	-0.027779	4.576752e+09	1.003158e+07	6.063303e+07
   3	0.409765	-0.028545	4.521058e+09	1.003305e+07	5.995173e+07

   >>> res.data()

   	run	timestamp	pool_value	arb_profits_percent	pool_volume	arb_profit	pool_fees
   0	0	2023-09-18 23:30:00+00:00	1.799787e+09	-0.000552	40480.098668	993516.570233	455541.247191
   1	0	2023-09-18 23:38:34+00:00	1.799580e+09	-0.000552	0.000000	0.000000	0.000000
   2	0	2023-09-18 23:47:08+00:00	1.799374e+09	-0.000552	0.000000	0.000000	0.000000
   3	0	2023-09-18 23:55:42+00:00	1.799167e+09	-0.000552	0.000000	0.000000	0.000000
   4	0	2023-09-19 00:04:17+00:00	1.798961e+09	-0.000552	0.000000	0.000000	0.000000
   ...	...	...	...	...	...	...	...
   40991	3	2023-11-18 22:55:42+00:00	1.922090e+09	-0.005379	0.000000	0.000000	0.000000
   40992	3	2023-11-18 23:04:17+00:00	1.922090e+09	-0.005379	0.000000	0.000000	0.000000
   40993	3	2023-11-18 23:12:51+00:00	1.922090e+09	-0.005379	0.000000	0.000000	0.000000
   40994	3	2023-11-18 23:21:25+00:00	1.922090e+09	-0.005379	0.000000	0.000000	0.000000
   40995	3	2023-11-18 23:30:00+00:00	1.922090e+09	-0.005379	0.000000	0.000000	0.000000
   40996 rows x 7 columns

Arbitrage simulations to see results of varying loan_discount and liquidation_discount parameters in `Controller`::

   >>> loan_discounts = [int(d * 10**18) for d in [0.09, 0.10, 0.11, 0.12]]
   >>> res = crvusdsim.autosim(pool="wstETH", sim_mode="controller", loan_discount=loan_discounts, liquidation_discount=[int(0.06 * 10**18)])

   [INFO][17:01:13][crvusdsim.pipelines.simple]-91016: Simulating mode: controller
   [INFO][17:01:15][curvesim.price_data.sources]-91016: Fetching CoinGecko price data...
   [INFO][17:02:56][crvusdsim.templates.Strategy]-91050: [Curve.fi Stablecoin wstETH] Simulating with {'loan_discount': 100000000000000000, 'liquidation_discount': 60000000000000000}
   [INFO][17:02:56][crvusdsim.templates.Strategy]-91052: [Curve.fi Stablecoin wstETH] Simulating with {'loan_discount': 110000000000000000, 'liquidation_discount': 60000000000000000}
   [INFO][17:02:56][crvusdsim.templates.Strategy]-91049: [Curve.fi Stablecoin wstETH] Simulating with {'loan_discount': 90000000000000000, 'liquidation_discount': 60000000000000000}
   [INFO][17:02:56][crvusdsim.templates.Strategy]-91053: [Curve.fi Stablecoin wstETH] Simulating with {'loan_discount': 120000000000000000, 'liquidation_discount': 60000000000000000}

   >>> res.summary()

   metric	averange_user_health	liquidations_count	liquidation_volume
   stat	mean	max	sum
   0	0.027328	0.0	0.0
   1	0.038743	0.0	0.0
   2	0.050414	0.0	0.0
   3	0.062351	0.0	0.0

   >>> res.data()

   	run	timestamp	averange_user_health	liquidations_count	liquidation_volume
   0	0	2023-09-18 23:30:00+00:00	0.036745	0.0	0.0
   1	0	2023-09-18 23:38:34+00:00	0.036745	0.0	0.0
   2	0	2023-09-18 23:47:08+00:00	0.036743	0.0	0.0
   3	0	2023-09-18 23:55:42+00:00	0.036739	0.0	0.0
   4	0	2023-09-19 00:04:17+00:00	0.036733	0.0	0.0
   ...	...	...	...	...	...
   40991	3	2023-11-18 22:55:42+00:00	0.045240	0.0	0.0
   40992	3	2023-11-18 23:04:17+00:00	0.045240	0.0	0.0
   40993	3	2023-11-18 23:12:51+00:00	0.045240	0.0	0.0
   40994	3	2023-11-18 23:21:25+00:00	0.045240	0.0	0.0
   40995	3	2023-11-18 23:30:00+00:00	0.045240	0.0	0.0
   40996 rows x 5 columns

Arbitrage simulations to see results of varying N of user's position::

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

   >>> res.summary()

   metric	user_value
   stat	annualized_returns
   0	-0.228595
   1	-0.168579
   2	-0.129110
   3	-0.104466
   4	-0.053433
   5	-0.027022
   6	-0.021667

   >>> res.data()

   	run	timestamp	user_value
   0	0	2023-09-18 23:30:00+00:00	1.000000
   1	0	2023-09-18 23:38:34+00:00	1.000000
   2	0	2023-09-18 23:47:08+00:00	1.000000
   3	0	2023-09-18 23:55:42+00:00	1.000000
   4	0	2023-09-19 00:04:17+00:00	1.000000
   ...	...	...	...
   71738	6	2023-11-18 22:55:42+00:00	0.996344
   71739	6	2023-11-18 23:04:17+00:00	0.996344
   71740	6	2023-11-18 23:12:51+00:00	0.996344
   71741	6	2023-11-18 23:21:25+00:00	0.996344
   71742	6	2023-11-18 23:30:00+00:00	0.996344
   71743 rows x 3 columns



Features
--------

crvUSDsim lets you:

* Simulate interactions with A series of objects related to crvusd in Python (include LLAMMA pool, Controller, PegKeepers, etc).
* Analyze the effects of parameter changes on pool performance
* Develop custom simulation pipelines for pool optimization


User Guide
-----------

.. toctree::
   :maxdepth: 2

   install
   quickstart


API Documentation
-----------------

.. toctree::
   :maxdepth: 2

   api


Contributor Guide
------------------

- Issue Tracker: github.com/0xreviews/crvusdsim/issues
- Source Code: github.com/0xreviews/crvusdsim

.. toctree::
   :maxdepth: 2

   contributing


Support
-------

If you are having issues, please let us know.  You can reach us via the following

|  GitHub: `crvUSDsim issues <https://github.com/0xreviews/crvusdsim/issues>`_


License
-------

Portions of the codebase are authorized derivatives of code owned by Curve.fi (Swiss Stake GmbH).  These are the vyper snippets used for testing and the python code derived from them (`crvusdsim/pool/crvusd`); there are copyright notices placed appropriately.  The rest of the codebase has an MIT license.
