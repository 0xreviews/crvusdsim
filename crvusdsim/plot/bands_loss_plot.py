import altair as alt
from pandas import DataFrame

def get_llamma_bands_loss(pool_state):
    x = []
    y = []
    z = []
    for data_per_run in pool_state:
        base_price = data_per_run.iloc[-1]["base_price"]
        A = data_per_run.iloc[-1]["A"]
        min_band = data_per_run.iloc[-1]["min_band"]
        max_band = data_per_run.iloc[-1]["max_band"]
        x += [A] * (max_band - min_band + 1)
        y += [round(base_price * ((A-1) / A) **i, 2) for i in range(min_band, max_band + 1)]
        z += data_per_run.iloc[-1]["bands_loss"]

    return DataFrame({
        "A": x,
        "price": y,
        "loss percent": z,
    })

def make_bands_loss_plot(results):
    source = get_llamma_bands_loss(results.pool_state)
    print("\nsource")
    print(source)
    chart = alt.Chart(source).mark_rect().encode(
        x='A:O',
        y='band index:O',
        color='loss percent:Q'
    )
    chart.save("bands_loss.html")
