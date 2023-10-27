import altair as alt
from pandas import DataFrame
import numpy as np


PRICE_INTERVAL = 20


def get_llamma_bands_loss(pool_state):
    last_run = pool_state[-1]
    A = last_run.iloc[-1]["A"]
    base_price = last_run.iloc[-1]["base_price"]
    min_price = base_price * ((A - 1) / A) ** (last_run.iloc[-1]["max_band"] + 1)
    max_price = base_price * ((A - 1) / A) ** (last_run.iloc[-1]["min_band"] - 1)
    price_ranges = [p for p in range(int(min_price), int(max_price), PRICE_INTERVAL)]
    print("\nprice_ranges")
    print(price_ranges)

    x = []
    y = []
    z = []
    for data_per_run in pool_state:
        base_price = data_per_run.iloc[-1]["base_price"]
        A = data_per_run.iloc[-1]["A"]
        min_band = data_per_run.iloc[-1]["min_band"]
        max_band = data_per_run.iloc[-1]["max_band"]

        bands_loss = data_per_run.iloc[-1]["bands_loss"]

        _xs = []
        _zs = []
        for i in range(len(bands_loss)):
            p_up = base_price * ((A - 1) / A) ** (max_band - i - 1)
            p_down = base_price * ((A - 1) / A) ** (max_band - i)
            loss_per_p = bands_loss[i] / (p_up - p_down)
            for j in range(len(price_ranges)):
                _p = price_ranges[j]
                if p_down <= _p and _p <= p_up:
                    _xs.append(_p)
                    _zs.append(loss_per_p * min(p_up - _p, PRICE_INTERVAL))
                else:
                    pass

        x += [A] * len(_xs)
        y += _xs
        z += _zs

    return DataFrame(
        {
            "A": x,
            "price": y,
            "loss percent": z,
        }
    )


def make_bands_loss_plot(results):
    source = get_llamma_bands_loss(results.state_data)
    print("\nsource")
    print(source)
    chart = (
        alt.Chart(source)
        .mark_rect()
        .encode(
            alt.X("A:O"), alt.Y("price:O").scale(reverse=True), color="loss percent:Q"
        )
        # .encode(
        #     alt.X("A:Q", bin=alt.Bin(maxbins=20)),
        #     alt.Y("price:Q", bin=alt.Bin(maxbins=40)),
        #     alt.Color("loss percent:Q", scale=alt.Scale(scheme="greenblue")),
        # )
    )
    chart.save("bands_loss.html")
