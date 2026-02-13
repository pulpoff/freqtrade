"""WhiteBit exchange subclass"""

import logging
from datetime import datetime

from freqtrade.enums import MarginMode, TradingMode
from freqtrade.exceptions import ExchangeError, OperationalException
from freqtrade.exchange import Exchange
from freqtrade.exchange.exchange_types import CcxtBalances, FtHas


logger = logging.getLogger(__name__)


class Whitebit(Exchange):
    """WhiteBit exchange class.
    Contains adjustments needed for Freqtrade to work with this exchange.
    """

    _ft_has: FtHas = {
        "trades_has_history": False,
    }
    _ft_has_futures: FtHas = {
        "uses_leverage_tiers": False,
        "mark_ohlcv_price": "futures",
    }

    _supported_trading_mode_margin_pairs: list[tuple[TradingMode, MarginMode]] = [
        (TradingMode.SPOT, MarginMode.NONE),
        (TradingMode.FUTURES, MarginMode.ISOLATED),
    ]

    def get_balances(self, params: dict | None = None) -> CcxtBalances:
        """
        WhiteBit returns None for free/used/total on some currencies.
        Sanitize these to 0 so downstream code (wallets, RPC) doesn't break.
        """
        balances = super().get_balances(params)
        # Log balances for debugging WhiteBit collateral wallet issues
        for currency in balances:
            if isinstance(balances[currency], dict):
                bal = balances[currency]
                logger.info(
                    f"WhiteBit balance {currency}: "
                    f"free={bal.get('free')}, used={bal.get('used')}, total={bal.get('total')}"
                )
                for key in ("free", "used", "total"):
                    if balances[currency].get(key) is None:
                        balances[currency][key] = 0
        return balances

    def get_max_leverage(self, pair: str, stake_amount: float | None) -> float:
        if self.trading_mode == TradingMode.FUTURES:
            return self.markets[pair]["limits"]["leverage"]["max"]
        else:
            return 1.0

    async def _fetch_funding_rate_history(
        self,
        pair: str,
        timeframe: str,
        limit: int,
        since_ms: int | None = None,
    ) -> list[list]:
        """
        WhiteBit does not support fetchFundingRateHistory.
        Return empty list so the data downloader skips funding rate candles
        gracefully instead of raising ccxt.NotSupported for every pair.
        """
        return []

    def get_funding_fees(
        self, pair: str, amount: float, is_short: bool, open_date: datetime
    ) -> float:
        """
        Fetch funding fees from the exchange.
        WhiteBit does not support fetchFundingRateHistory, so the dry-run
        calculation path cannot work.  In live mode we use fetchFundingHistory
        (the proper exchange API).  In dry-run mode funding fees are unavailable.
        """
        if self.trading_mode == TradingMode.FUTURES:
            if not self._config["dry_run"]:
                try:
                    return self._get_funding_fees_from_exchange(pair, open_date)
                except (ExchangeError, OperationalException):
                    logger.warning(f"Could not update funding fees for {pair}.")
        return 0.0
