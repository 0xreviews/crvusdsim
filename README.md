# crvUSDsim

crvUSDsim is a tool simulating crvUSD pools with optimal arbitrageurs trading against them to check parameters for onboarding new collateral. Its primary use is to determine optimal A (a measure of the concentration of liquidity), fee parameters, loan_discount given historical price and volume feeds, liquidation_discount, policy_rate.

## Features

- Simulate interactions with crvUSD pools in Python
- Analyze the effects of parameter changes on pool performance
- Develop custom simulation tools for parameters optimization
- Simulate the anti-risk ability of the protocol in extreme cases

## Quick Start

```bash
poetry install
poetry shell
```
