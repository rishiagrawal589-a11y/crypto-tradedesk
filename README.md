
# Crypto TradeDesk

A simple crypto trading dashboard for **signals, risk sizing, and paper/backtest analysis**.

### What it does
- Pulls live public Binance candle data (no API key required)
- Supports BTC, ETH, SOL, BNB and XRP
- Timeframes: 15m, 1h, 4h, 1d
- Uses EMA20/EMA50 + RSI for directional signals
- Uses ATR to calculate stop distance
- Calculates position size from a fixed % of capital at risk
- Shows a 2R target
- Runs a basic historical backtest
- Does **not** place real trades

### Run locally

```bash
pip install streamlit requests pandas numpy
streamlit run app.py
```

Then open the local Streamlit address shown in your terminal.

### Strategy
LONG when:
- price > EMA20 > EMA50
- RSI is 50–70

SHORT when:
- price < EMA20 < EMA50
- RSI is 30–50

Stop = 1.5 × ATR by default.
Target = 2R by default.

This is a research/paper-trading tool, not financial advice. Before risking money, test the strategy over multiple market regimes and include fees, slippage, funding and liquidation risk.
