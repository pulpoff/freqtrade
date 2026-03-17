# <img src="docs/assets/icon.svg" alt="freqtrade icon" height="32"> freqtrade

An improved and further developed fork of [Freqtrade](https://github.com/freqtrade/freqtrade) — the free and open source crypto trading bot — focused on providing a completely new WebGUI inspired by [botcrypto.io](https://botcrypto.io).
[![Freqtrade CI](https://github.com/freqtrade/freqtrade/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/freqtrade/freqtrade/actions/workflows/ci.yml)
[![DOI](https://joss.theoj.org/papers/10.21105/joss.04864/status.svg)](https://doi.org/10.21105/joss.04864)
[![codecov](https://codecov.io/gh/freqtrade/freqtrade/branch/develop/graph/badge.svg?token=AD5BG3ATKI)](https://codecov.io/gh/freqtrade/freqtrade)
[![Documentation](https://readthedocs.org/projects/freqtrade/badge/)](https://www.freqtrade.io)
[![Discord Server](https://img.shields.io/badge/Freqtrade_Discord-4E4E4E?logo=discord)](https://discord.gg/p7nuUNVfP7)

The goal is to bring a no-code visual strategy builder, real-time trade monitoring, and a modern dashboard experience to Freqtrade — similar to what botcrypto.io offered with its drag-and-drop editor, TradingView widgets, and cloud-based bot management — but fully open source and self-hosted.

## New WebGUI (In Development)

- **Visual Strategy Editor** — Drag-and-drop strategy builder with technical indicators, no coding required
- **Real-Time Dashboard** — Live trade monitoring with TradingView-style charting and bot performance metrics
- **Strategy Store** — Browse, share, and import community-built strategies
- **Backtesting UI** — Run and visualize backtests directly from the browser
- **Notifications** — Discord, webhooks, and Telegram alerts from the GUI

## Core Features

- **All Freqtrade Features** — Backtesting, hyperopt, FreqAI, Telegram control, dry-run mode, and more
- **Performance Optimized** — Reduced redundant DB queries, O(n) filtering, thread-safe singletons, vectorized analysis
- **15+ Exchanges** — Binance, Bybit, OKX, Bitget, Gate.io, Kraken, HTX, Hyperliquid, BingX, Bitmart, and more
- **WhiteBit Support** — Full spot and futures trading on [WhiteBit](https://whitebit.com/) with ccxt compatibility fixes (in addition to all other supported exchanges)

## Quick Start

```bash
git clone https://github.com/pulpoff/freqtrade.git
cd freqtrade
./setup.sh -i
freqtrade trade --config user_data/config.json --strategy YourStrategy
```

See the full [Freqtrade documentation](https://www.freqtrade.io) for detailed setup and configuration.

## Monitoring

Pair with [freqmon](https://github.com/pulpoff/freqmon) for multi-instance monitoring dashboard.

## Disclaimer

This software is for educational purposes only. Do not risk money which you are afraid to lose. Use the software at your own risk. The authors assume no responsibility for your trading results.

## License

[GPLv3](LICENSE)
