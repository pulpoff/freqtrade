"""WhiteBit exchange subclass"""

import logging
from datetime import datetime

from freqtrade.enums import MarginMode, TradingMode
from freqtrade.exceptions import ExchangeError, OperationalException
from freqtrade.exchange import Exchange
from freqtrade.exchange.exchange_types import CcxtBalances, FtHas


logger = logging.getLogger(__name__)


class Whitebit(Exchange):
    """
    WhiteBit exchange class. Contains adjustments needed for Freqtrade to work
    with this exchange.

    Please note that this exchange is not included in the list of exchanges
    officially supported by the Freqtrade development team. So some features
    may still not work as expected.
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
        WhiteBit collateral endpoint only returns total per currency,
        ccxt leaves free/used as None. Derive the missing values.
        """
        balances = super().get_balances(params)
        for currency in balances:
            if isinstance(balances[currency], dict):
                bal = balances[currency]
                if bal.get("used") is None:
                    bal["used"] = 0
                if bal.get("free") is None:
                    bal["free"] = (bal.get("total") or 0) - bal["used"]
                if bal.get("total") is None:
                    bal["total"] = 0
        return balances

    def get_max_leverage(self, pair: str, stake_amount: float | None) -> float:
        # No leverage tiers - read max from market info directly
        if self.trading_mode == TradingMode.FUTURES:
            return self.markets[pair]["limits"]["leverage"]["max"]
        return 1.0

    async def _fetch_funding_rate_history(
        self,
        pair: str,
        timeframe: str,
        limit: int,
        since_ms: int | None = None,
    ) -> list[list]:
        # WhiteBit does not support fetchFundingRateHistory
        return []

    def get_funding_fees(
        self, pair: str, amount: float, is_short: bool, open_date: datetime
    ) -> float:
        """
        Fetch funding fees from the exchange.
        :param pair: The quote/base pair of the trade
        :param is_short: trade direction
        :param amount: Trade amount
        :param open_date: Open date of the trade
        :return: funding fee since open_date
        :raises: ExchangeError if something goes wrong.
        """
        # WhiteBit does not provide fetchFundingRateHistory,
        # use fetchFundingHistory via _get_funding_fees_from_exchange instead.
        if self.trading_mode == TradingMode.FUTURES:
            if not self._config["dry_run"]:
                try:
                    return self._get_funding_fees_from_exchange(pair, open_date)
                except (ExchangeError, OperationalException):
                    logger.warning(f"Could not update funding fees for {pair}.")
        return 0.0
