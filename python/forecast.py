"""
Demand forecasting by material and plant, with automatic model selection.

For each series of 24 monthly consumption values:
  1. Hold out the last 6 months.
  2. Fit four candidate methods on the first 18 and forecast the 6 held-out months:
       naive              last observed value
       moving_avg_3       mean of the last 3 months
       ses                simple exponential smoothing, alpha tuned on 1-step-ahead error
       seasonal_naive     same month last year (captures seasonality)
  3. Score each with WAPE (sum |actual - forecast| / sum actual) and keep the best.
  4. Refit the winner on all 24 months and forecast the next 3 months.

The naive method's WAPE is kept as a benchmark, so the report can show how much
the chosen model beats "assume next month looks like last month".
"""
from datetime import date

import numpy as np

HOLDOUT = 6
HORIZON = 3


def wape(actual, fcst):
    actual, fcst = np.asarray(actual, float), np.asarray(fcst, float)
    total = actual.sum()
    if total == 0:
        return 0.0 if np.allclose(fcst, 0) else 100.0
    return float(np.abs(actual - fcst).sum() / total * 100)


def _ses_level(y, alpha):
    level = y[0]
    for v in y[1:]:
        level = alpha * v + (1 - alpha) * level
    return level


def _best_alpha(y):
    best, best_sse = 0.3, np.inf
    for alpha in np.arange(0.1, 0.95, 0.1):
        level, sse = y[0], 0.0
        for v in y[1:]:
            sse += (v - level) ** 2
            level = alpha * v + (1 - alpha) * level
        if sse < best_sse:
            best, best_sse = float(alpha), sse
    return best


def predict(method, history, steps):
    """Forecast `steps` periods ahead from `history` with one method."""
    y = np.asarray(history, float)
    if method == "naive":
        return np.repeat(y[-1], steps)
    if method == "moving_avg_3":
        return np.repeat(y[-3:].mean(), steps)
    if method == "ses":
        return np.repeat(_ses_level(y, _best_alpha(y)), steps)
    if method == "seasonal_naive":
        if len(y) < 12:
            return np.repeat(y[-1], steps)
        return np.array([y[len(y) - 12 + (i % 12)] for i in range(steps)])
    raise ValueError(method)


METHODS = ["naive", "moving_avg_3", "ses", "seasonal_naive"]


def select_and_forecast(history):
    """Return (best_method, best_wape, naive_wape, forecast for HORIZON periods)."""
    train, test = history[:-HOLDOUT], history[-HOLDOUT:]
    scores = {m: wape(test, predict(m, train, HOLDOUT)) for m in METHODS}
    best = min(METHODS, key=lambda m: (scores[m], METHODS.index(m)))
    fcst = np.clip(predict(best, history, HORIZON), 0, None)
    return best, scores[best], scores["naive"], fcst


def next_months(last_period: date, n: int):
    y, m, out = last_period.year, last_period.month, []
    for _ in range(n):
        m += 1
        if m == 13:
            y, m = y + 1, 1
        out.append(date(y, m, 1))
    return out


def run(con):
    """Read consumption from the database, write forecast and forecast_accuracy."""
    rows = con.execute(
        "SELECT matnr, werks, period, qty FROM consumption ORDER BY matnr, werks, period"
    ).fetchall()
    series = {}
    for matnr, werks, period, qty in rows:
        series.setdefault((matnr, werks), []).append((period, qty))

    con.execute("DELETE FROM forecast")
    con.execute("DELETE FROM forecast_accuracy")
    picks = {}
    for (matnr, werks), pts in series.items():
        history = [q for _, q in pts]
        if len(history) < HOLDOUT + 6:
            continue
        method, best_wape, naive_wape, fcst = select_and_forecast(history)
        last = date.fromisoformat(pts[-1][0])
        for period, q in zip(next_months(last, HORIZON), fcst):
            con.execute("INSERT INTO forecast VALUES (?,?,?,?,?)",
                        (matnr, werks, period.isoformat(), round(float(q), 1), method))
        con.execute("INSERT INTO forecast_accuracy VALUES (?,?,?,?,?)",
                    (matnr, werks, method, round(best_wape, 1), round(naive_wape, 1)))
        picks[method] = picks.get(method, 0) + 1
    con.commit()
    return picks
