"""WhiteBit exchange subclass"""

import logging
from datetime import datetime

import ccxt

from freqtrade.enums import MarginMode, TradingMode
from freqtrade.exceptions import DDosProtection, ExchangeError, OperationalException, TemporaryError
from freqtrade.exchange import Exchange
from freqtrade.exchange.common import retrier
from freqtrade.exchange.exchange_types import CcxtBalances, CcxtOrder, CcxtPosition, FtHas


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
        # WS disabled: ccxt.pro stores WhiteBit candles under 'unknown' timeframe key
        # because the WS API doesn't include timeframe in candle updates.
        # Freqtrade expects candles keyed by timeframe ('1m', '5m', etc.), so WS
        # data is never found and every tick falls back to REST with log spam.
        "ws_enabled": False,
    }
    _ft_has_futures: FtHas = {
        "uses_leverage_tiers": False,
        "mark_ohlcv_price": "futures",
    }

    _supported_trading_mode_margin_pairs: list[tuple[TradingMode, MarginMode]] = [
        (TradingMode.SPOT, MarginMode.NONE),
        (TradingMode.FUTURES, MarginMode.ISOLATED),
    ]

    def reload_markets(self, force: bool = False, *, load_leverage_tiers: bool = True) -> None:
        super().reload_markets(force=force, load_leverage_tiers=load_leverage_tiers)
        # Fix contractSize in ccxt's own market dicts.
        # ccxt sets contractSize = amountPrecision for WhiteBit (e.g. 0.01 for BCH)
        # but WhiteBit expects amounts in base currency, not contracts.
        # ccxt's safe_order() uses market['contractSize'] internally to calculate
        # average price: avg = cost / (filled * contractSize). With contractSize=0.01,
        # the average price gets inflated 100x (e.g. BCH shows 56356 instead of 563.56).
        if self.trading_mode == TradingMode.FUTURES:
            for api in (self._api, self._api_async):
                for market in api.markets.values():
                    if market.get("contract"):
                        market["contractSize"] = 1

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
            try:
                max_lev = self.markets[pair]["limits"]["leverage"]["max"]
                if max_lev is not None:
                    return float(max_lev)
            except (KeyError, TypeError, ValueError):
                pass
            logger.info(f"Could not read max leverage for {pair}, defaulting to 10.")
            return 10.0
        return 1.0

    def get_contract_size(self, pair: str) -> float | None:
        # ccxt sets contractSize = amountPrecision for WhiteBit (e.g. 0.01 for BCH),
        # but WhiteBit expects order amounts in base currency, not contracts.
        # This causes freqtrade to inflate amounts by 1/contractSize (e.g. 100x for BCH).
        if self.trading_mode == TradingMode.FUTURES:
            return 1.0
        return 1

    def _order_contracts_to_amount(self, order: CcxtOrder) -> CcxtOrder:
        """
        Fix average price inflated by ccxt's wrong contractSize for WhiteBit futures.

        ccxt sets contractSize = amountPrecision for WhiteBit (e.g. 0.01 for SOL).
        Its safe_order() then calculates: average = cost / (filled * 0.01) = 100x actual.
        The reload_markets() fix patches market dicts, but ccxt methods call load_markets()
        internally which can use stale references. Recalculate average here as cost/filled
        (correct for contractSize=1) to guarantee correct prices at all entry points.
        """
        if self.trading_mode == TradingMode.FUTURES:
            filled = order.get("filled")
            cost = order.get("cost")
            if filled and cost and filled > 0:
                order["average"] = cost / filled
        return order

    def fetch_positions(
        self, pair: str | None = None, params: dict | None = None
    ) -> list[CcxtPosition]:
        """
        Fix WhiteBit positions: ccxt parse_position sets side=None and contracts=None.

        Without side, _update_live() in wallets.py filters out all positions
        (``if position["side"] is None: continue``), leaving _positions empty.
        This causes _check_exit_amount() to always return False, triggering an
        infinite recovery loop that prevents exits.

        Derive side from the raw amount sign (+long/-short) and set contracts
        from the absolute amount.
        """
        positions = super().fetch_positions(pair, params)
        for position in positions:
            info = position.get("info", {})
            raw_amount = float(info.get("amount", 0))
            if position.get("side") is None and raw_amount != 0:
                position["side"] = "long" if raw_amount > 0 else "short"
            if position.get("contracts") is None:
                position["contracts"] = abs(raw_amount)
        return positions

    def _set_leverage(
        self,
        leverage: float,
        pair: str | None = None,
        accept_fail: bool = False,
    ):
        # WhiteBit does not support per-symbol setLeverage via API.
        # Leverage is configured at the account/position level on the exchange.
        pass

    def set_margin_mode(
        self,
        pair: str,
        margin_mode: MarginMode,
        accept_fail: bool = False,
        params: dict | None = None,
    ):
        # WhiteBit only supports isolated margin for futures — no API call needed.
        pass

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
        if self.trading_mode == TradingMode.FUTURES:
            try:
                if self._config["dry_run"]:
                    return self._fetch_and_calculate_funding_fees(
                        pair, amount, is_short, open_date
                    )
                else:
                    return self._get_funding_fees_from_exchange(pair, open_date)
            except (ExchangeError, OperationalException):
                logger.warning(f"Could not update funding fees for {pair}.")
        return 0.0

    @retrier(retries=0)
    def _fetch_orders(
        self, pair: str, since: datetime, params: dict | None = None
    ) -> list[CcxtOrder]:
        """
        WhiteBit's ccxt fetch_orders() is broken — it uses asyncio.gather()
        on synchronous methods, causing TypeError. Bypass it and fetch
        open + closed orders separately.
        """
        if self._config["dry_run"]:
            return []
        try:
            since_ms = int((since.timestamp() - 10) * 1000)
            orders = self._fetch_orders_emulate(pair, since_ms)
            self._log_exchange_response("fetch_orders", orders)
            orders = [self._order_contracts_to_amount(o) for o in orders]
            return orders
        except ccxt.DDoSProtection as e:
            raise DDosProtection(e) from e
        except (ccxt.OperationFailed, ccxt.ExchangeError) as e:
            raise TemporaryError(
                f"Could not fetch orders due to {e.__class__.__name__}. Message: {e}"
            ) from e
        except ccxt.BaseError as e:
            raise OperationalException(e) from e
