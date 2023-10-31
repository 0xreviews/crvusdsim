import altair as alt
from pandas import DataFrame, concat
import numpy as np
from altair import hconcat

PRICE_INTERVAL = 5


def get_prices_timeseries(prices, price_ranges):
    prices.columns = ["Price($)"]
    prices.astype("float64")
    kwargs = {
        "data": prices.reset_index(),
        "title": "Price Chart",
        "mark": {"type": "line", "interpolate": "monotone"},
        "encoding": {
            "x": alt.X("index:T", title=None),
            "y": alt.Y("Price($):O")
            .axis(format=".2f", labelOverlap=True)
            .scale(
                zero=False,
                reverse=True,
                # domain=[min(price_ranges), max(price_ranges)],
                scheme="viridis",
            ),
        },
        "height": 400,
        "width": 300,
    }
    prices_chart = alt.Chart(**kwargs)
    return prices_chart.interactive()


def make_bands_arb_profits_plot(state_data, prices):
    # use max A to calculate prices range
    max_A_index = 0
    max_A = 0
    for i in range(len(state_data)):
        if state_data[i]["A"].iloc[0] > max_A:
            max_A = state_data[i]["A"].iloc[0]
            max_A_index = i

    last_run = state_data[max_A_index]
    A = last_run.iloc[max_A_index]["A"]
    base_price = last_run.iloc[-1]["base_price"]
    min_price = base_price * ((A - 1) / A) ** (last_run.iloc[-1]["max_band"] + 1)
    max_price = base_price * ((A - 1) / A) ** (last_run.iloc[-1]["min_band"] - 1)
    price_ranges = [p for p in range(int(min_price), int(max_price), PRICE_INTERVAL)]

    x = []
    y = []
    z = []
    for data_per_run in state_data:
        base_price = data_per_run.iloc[-1]["base_price"]
        A = data_per_run.iloc[-1]["A"]
        min_band = data_per_run.iloc[-1]["min_band"]
        max_band = data_per_run.iloc[-1]["max_band"]

        bands_arb_profits = data_per_run.iloc[-1]["bands_arb_profits"]

        _xs = []
        _zs = []
        for i in range(len(bands_arb_profits)):
            p_up = base_price * ((A - 1) / A) ** (max_band - i - 1)
            p_down = base_price * ((A - 1) / A) ** (max_band - i)
            profits_per_p = bands_arb_profits[i] / (p_up - p_down)
            for j in range(len(price_ranges)):
                _p = price_ranges[j]
                if p_down <= _p and _p <= p_up:
                    _xs.append(_p)
                    _zs.append(profits_per_p * min(p_up - _p, PRICE_INTERVAL) * 100)
                else:
                    pass

        x += [A] * len(_xs)
        y += _xs
        z += _zs

    source = DataFrame(
        {
            "x": x,
            "y": y,
            "z": z,
        }
    )

    bands_chart = alt.Chart(
        data=source,
        mark="rect",
        encoding=alt.Encoding(
            x=alt.X("x:O").title("A"),
            y=alt.Y("y:O")
            .scale(reverse=True)
            .axis(labelOverlap=True)
            .title("Price($)"),
            color=alt.Color("z:Q", scale=alt.Scale(scheme="blues")).title("Profits(%)"),
        ),
        title=alt.TitleParams(
            text="Bands Arbitrageur Profits(%)",
            fontSize=16,
            align="left",
            anchor="start",
            offset=16,
        ),
        height=400,
        width=300,
    ).interactive()

    prices_chart = get_prices_timeseries(prices, price_ranges)

    chart = hconcat(bands_chart, prices_chart).resolve_scale(color="independent")

    return chart
