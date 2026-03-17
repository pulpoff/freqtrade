# <img src="docs/assets/icon.svg" alt="freqtrade icon" height="32"> freqtrade

An improved and further developed version of [Freqtrade](https://github.com/freqtrade/freqtrade) — free and open source crypto trading bot — to provide a new WebGUI based on [botcrypto.io](https://botcrypto.io).

## Features

- **New WebGUI** — Modern web interface inspired by botcrypto.io for strategy management and live monitoring
- **WhiteBit Support** — Spot and futures trading on [WhiteBit](https://whitebit.com/) with full ccxt compatibility fixes
- **Performance Optimized** — Reduced redundant DB queries, O(n) filtering, thread-safe singletons, vectorized analysis
- **All Freqtrade Features** — Backtesting, hyperopt, FreqAI, Telegram control, and 15+ supported exchanges

## Quick Start

```bash
git clone https://github.com/pulpoff/freqtrade.git
cd freqtrade
./setup.sh -i
freqtrade trade --config user_data/config.json --strategy YourStrategy
```

See the full [Freqtrade documentation](https://www.freqtrade.io) for detailed setup and configuration.

## Supported Exchanges

Binance, Bybit, OKX, Bitget, Gate.io, Kraken, HTX, Hyperliquid, BingX, Bitmart, WhiteBit, and [more](https://www.freqtrade.io/en/stable/exchanges/).

## Monitoring

Pair with [freqmon](https://github.com/pulpoff/freqmon) for multi-instance monitoring dashboard.

## Disclaimer

This software is for educational purposes only. Do not risk money which you are afraid to lose. Use the software at your own risk. The authors assume no responsibility for your trading results.

## License

[GPLv3](LICENSE)
