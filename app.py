
import math
import requests
import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(page_title="Crypto TradeDesk", page_icon="₿", layout="wide")

BINANCE = "https://api.binance.com/api/v3/klines"

@st.cache_data(ttl=30)
def get_ohlcv(symbol="BTCUSDT", interval="1h", limit=500):
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    r = requests.get(BINANCE, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    cols = ["time","open","high","low","close","volume","close_time","qav","trades",
            "tbbav","tbqav","ignore"]
    df = pd.DataFrame(data, columns=cols)
    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c])
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df[["time","open","high","low","close","volume"]]

def indicators(df):
    x = df.copy()
    x["ema20"] = x.close.ewm(span=20, adjust=False).mean()
    x["ema50"] = x.close.ewm(span=50, adjust=False).mean()
    delta = x.close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    x["rsi"] = 100 - (100 / (1 + rs))
    prev = x.close.shift(1)
    tr = pd.concat([
        x.high - x.low,
        (x.high - prev).abs(),
        (x.low - prev).abs()
    ], axis=1).max(axis=1)
    x["atr"] = tr.rolling(14).mean()
    x["vol_ma"] = x.volume.rolling(20).mean()
    return x

def signal(row):
    if pd.isna(row.ema50) or pd.isna(row.rsi) or pd.isna(row.atr):
        return "WAIT"
    bullish = row.close > row.ema20 > row.ema50
    bearish = row.close < row.ema20 < row.ema50
    if bullish and 50 <= row.rsi <= 70:
        return "LONG"
    if bearish and 30 <= row.rsi <= 50:
        return "SHORT"
    return "WAIT"

def backtest(df, fee=0.001):
    x = indicators(df).dropna().copy()
    x["sig"] = x.apply(signal, axis=1)
    position = 0
    entry = 0.0
    equity = 1.0
    equity_curve = []
    trades = []
    for i, row in x.iterrows():
        s = row.sig
        price = row.close
        if position == 0 and s in ("LONG","SHORT"):
            position = 1 if s == "LONG" else -1
            entry = price
            equity *= (1 - fee)
        elif position == 1 and s != "LONG":
            ret = price / entry - 1
            equity *= (1 + ret) * (1 - fee)
            trades.append(ret)
            position, entry = 0, 0
        elif position == -1 and s != "SHORT":
            ret = entry / price - 1
            equity *= (1 + ret) * (1 - fee)
            trades.append(ret)
            position, entry = 0, 0
        equity_curve.append(equity)
    if position:
        price = x.iloc[-1].close
        ret = price / entry - 1 if position == 1 else entry / price - 1
        equity *= (1 + ret) * (1 - fee)
        trades.append(ret)
        equity_curve[-1] = equity
    curve = pd.Series(equity_curve, index=x.time)
    peak = curve.cummax()
    dd = curve / peak - 1
    return x, curve, trades, dd.min()

st.title("₿ Crypto TradeDesk")
st.caption("Signal + risk dashboard. Paper-trading only — no exchange orders are sent.")

with st.sidebar:
    symbol = st.selectbox("Asset", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"])
    interval = st.selectbox("Timeframe", ["15m", "1h", "4h", "1d"], index=1)
    capital = st.number_input("Trading capital (USDT)", min_value=100.0, value=1000.0, step=100.0)
    risk_pct = st.number_input("Risk per trade (%)", min_value=0.1, max_value=5.0, value=1.0, step=0.1)
    atr_mult = st.number_input("Stop distance (ATR ×)", min_value=0.5, max_value=5.0, value=1.5, step=0.25)

try:
    raw = get_ohlcv(symbol, interval)
    df = indicators(raw)
    last = df.iloc[-1]
    sig = signal(last)

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Price", f"${last.close:,.2f}")
    c2.metric("Signal", sig)
    c3.metric("RSI", f"{last.rsi:.1f}")
    c4.metric("EMA 20 / 50", f"{last.ema20:,.0f} / {last.ema50:,.0f}")
    c5.metric("ATR", f"{last.atr:,.2f}")

    stop_dist = last.atr * atr_mult
    if sig == "LONG":
        stop = last.close - stop_dist
        target = last.close + stop_dist * 2
        side = "Long"
    elif sig == "SHORT":
        stop = last.close + stop_dist
        target = last.close - stop_dist * 2
        side = "Short"
    else:
        stop = target = np.nan
        side = "No trade"

    if sig != "WAIT":
        risk_money = capital * risk_pct / 100
        qty = risk_money / stop_dist
        notional = qty * last.close
        st.subheader("Trade plan")
        p1,p2,p3,p4 = st.columns(4)
        p1.metric("Side", side)
        p2.metric("Stop", f"${stop:,.2f}")
        p3.metric("2R Target", f"${target:,.2f}")
        p4.metric("Position size", f"{qty:.5f} {symbol[:-4]}")

        st.info(
            f"Risk budget: ${risk_money:.2f}. Approx. position notional: "
            f"${notional:,.2f}. This is a calculation, not an order."
        )
    else:
        st.info("No trade right now. Wait for trend + RSI conditions to align.")

    chart = df.set_index("time")[["close","ema20","ema50"]].tail(250)
    st.subheader("Price & trend")
    st.line_chart(chart)

    st.subheader("Recent candles / indicators")
    view = df[["time","close","ema20","ema50","rsi","atr","volume"]].tail(15).copy()
    st.dataframe(view, use_container_width=True, hide_index=True)

    st.subheader("Strategy backtest")
    bt, curve, trades, max_dd = backtest(raw)
    b1,b2,b3 = st.columns(3)
    total_return = (curve.iloc[-1]-1)*100
    win_rate = (sum(t > 0 for t in trades)/len(trades)*100) if trades else 0
    b1.metric("Backtest return", f"{total_return:.1f}%")
    b2.metric("Win rate", f"{win_rate:.1f}%")
    b3.metric("Max drawdown", f"{max_dd*100:.1f}%")
    st.line_chart(curve.rename("Equity"))

    st.caption(
        "Model: EMA20/EMA50 trend filter + RSI + ATR risk sizing. "
        "Backtest is illustrative and ignores slippage/funding/liquidation effects."
    )
except Exception as e:
    st.error(f"Could not load market data: {e}")
    st.write("Check your internet connection or try again in a moment.")
