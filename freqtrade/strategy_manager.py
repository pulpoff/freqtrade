"""
Strategy Manager - manages multiple FreqtradeBot instances in separate threads.

Each strategy runs in its own thread with its own FreqtradeBot, exchange connection,
database, and configuration. Strategies can be started/stopped independently.
"""

import copy
import logging
import threading
import time
import traceback
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from freqtrade.constants import PROCESS_THROTTLE_SECS, RETRY_TIMEOUT
from freqtrade.enums import RPCMessageType, State
from freqtrade.exceptions import OperationalException, TemporaryError
from freqtrade.exchange import timeframe_to_next_date


logger = logging.getLogger(__name__)


class StrategyStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPING = "stopping"


class StrategyInstance:
    """Represents a single running strategy with its own FreqtradeBot thread."""

    def __init__(self, strategy_id: str, config: dict[str, Any]):
        self.strategy_id = strategy_id
        self.config = config
        self.status = StrategyStatus.STOPPED
        self.error_message: str | None = None
        self.thread: threading.Thread | None = None
        self.bot = None  # FreqtradeBot instance
        self._stop_event = threading.Event()
        self.started_at: datetime | None = None
        self.stopped_at: datetime | None = None

    @property
    def strategy_name(self) -> str:
        return self.config.get("strategy", "Unknown")

    @property
    def exchange_name(self) -> str:
        return self.config.get("exchange", {}).get("name", "Unknown")

    @property
    def trading_mode(self) -> str:
        return self.config.get("trading_mode", "spot")

    @property
    def is_dry_run(self) -> bool:
        return self.config.get("dry_run", True)

    @property
    def stake_currency(self) -> str:
        return self.config.get("stake_currency", "USDT")

    @property
    def pairs(self) -> list[str]:
        return self.config.get("exchange", {}).get("pair_whitelist", [])

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API responses."""
        result = {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "exchange": self.exchange_name,
            "trading_mode": self.trading_mode,
            "dry_run": self.is_dry_run,
            "stake_currency": self.stake_currency,
            "pairs": self.pairs,
            "status": self.status.value,
            "error": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
        }
        # Add live stats if bot is running
        if self.bot and self.status == StrategyStatus.RUNNING:
            try:
                result["bot_state"] = self.bot.state.name if self.bot.state else "UNKNOWN"
            except Exception:
                result["bot_state"] = "UNKNOWN"
        return result


class StrategyManager:
    """
    Manages multiple FreqtradeBot instances running in parallel threads.

    Each strategy gets its own:
    - FreqtradeBot instance
    - Exchange connection
    - Database (separate SQLite file per strategy)
    - Thread for the trading loop
    """

    def __init__(self, base_config: dict[str, Any]):
        self._base_config = base_config
        self._strategies: dict[str, StrategyInstance] = {}
        self._lock = threading.Lock()
        logger.info("StrategyManager initialized")

    @property
    def strategies(self) -> dict[str, StrategyInstance]:
        return self._strategies

    def list_strategies(self) -> list[dict[str, Any]]:
        """Return status of all managed strategies."""
        with self._lock:
            return [inst.to_dict() for inst in self._strategies.values()]

    def get_strategy(self, strategy_id: str) -> StrategyInstance | None:
        """Get a specific strategy instance."""
        return self._strategies.get(strategy_id)

    def get_strategy_bot(self, strategy_id: str):
        """Get the FreqtradeBot for a specific strategy (for RPC calls)."""
        inst = self._strategies.get(strategy_id)
        if inst and inst.bot and inst.status == StrategyStatus.RUNNING:
            return inst.bot
        return None

    def add_strategy(self, strategy_id: str, config: dict[str, Any]) -> StrategyInstance:
        """Register a new strategy (does not start it)."""
        with self._lock:
            if strategy_id in self._strategies:
                raise OperationalException(f"Strategy '{strategy_id}' already exists")

            inst = StrategyInstance(strategy_id, config)
            self._strategies[strategy_id] = inst
            logger.info(f"Strategy '{strategy_id}' added ({config.get('strategy', '?')})")
            return inst

    def remove_strategy(self, strategy_id: str) -> None:
        """Remove a strategy (must be stopped first)."""
        with self._lock:
            inst = self._strategies.get(strategy_id)
            if not inst:
                raise OperationalException(f"Strategy '{strategy_id}' not found")
            if inst.status in (StrategyStatus.RUNNING, StrategyStatus.STARTING):
                raise OperationalException(
                    f"Strategy '{strategy_id}' is running. Stop it first."
                )
            del self._strategies[strategy_id]
            logger.info(f"Strategy '{strategy_id}' removed")

    def start_strategy(self, strategy_id: str) -> StrategyInstance:
        """Start a strategy in a new thread."""
        with self._lock:
            inst = self._strategies.get(strategy_id)
            if not inst:
                raise OperationalException(f"Strategy '{strategy_id}' not found")
            if inst.status in (StrategyStatus.RUNNING, StrategyStatus.STARTING):
                raise OperationalException(f"Strategy '{strategy_id}' is already running")

            inst.status = StrategyStatus.STARTING
            inst.error_message = None
            inst._stop_event.clear()

            thread = threading.Thread(
                target=self._run_strategy,
                args=(inst,),
                name=f"strategy-{strategy_id}",
                daemon=True,
            )
            inst.thread = thread
            thread.start()
            return inst

    def stop_strategy(self, strategy_id: str) -> StrategyInstance:
        """Signal a strategy to stop."""
        with self._lock:
            inst = self._strategies.get(strategy_id)
            if not inst:
                raise OperationalException(f"Strategy '{strategy_id}' not found")
            if inst.status not in (StrategyStatus.RUNNING, StrategyStatus.STARTING, StrategyStatus.PAUSED):
                raise OperationalException(
                    f"Strategy '{strategy_id}' is not running (status: {inst.status.value})"
                )

            inst.status = StrategyStatus.STOPPING
            inst._stop_event.set()
            logger.info(f"Strategy '{strategy_id}' stop requested")
            return inst

    def stop_all(self) -> None:
        """Stop all running strategies (used during shutdown)."""
        for sid, inst in list(self._strategies.items()):
            if inst.status in (StrategyStatus.RUNNING, StrategyStatus.STARTING, StrategyStatus.PAUSED):
                try:
                    self.stop_strategy(sid)
                except Exception as e:
                    logger.error(f"Error stopping strategy '{sid}': {e}")

        # Wait for all threads to finish (with timeout)
        for sid, inst in list(self._strategies.items()):
            if inst.thread and inst.thread.is_alive():
                inst.thread.join(timeout=10)

    def _run_strategy(self, inst: StrategyInstance) -> None:
        """
        Main loop for a strategy thread. Creates a FreqtradeBot and runs it.
        This runs in a separate thread.
        """
        from freqtrade.freqtradebot import FreqtradeBot
        from freqtrade.persistence import Trade

        strategy_id = inst.strategy_id
        logger.info(f"Strategy thread '{strategy_id}' starting...")

        try:
            # Build per-strategy config
            config = self._build_strategy_config(inst.config, strategy_id)

            # Create the bot
            bot = FreqtradeBot(config)
            inst.bot = bot
            inst.status = StrategyStatus.RUNNING
            inst.started_at = datetime.now(timezone.utc)

            # Set bot to running state
            bot.state = State.RUNNING
            bot.startup()

            logger.info(
                f"Strategy '{strategy_id}' ({inst.strategy_name}) running on "
                f"{inst.exchange_name} [{inst.trading_mode}]"
            )

            # Main trading loop
            throttle_secs = config.get("internals", {}).get(
                "process_throttle_secs", PROCESS_THROTTLE_SECS
            )

            while not inst._stop_event.is_set():
                try:
                    self._process_iteration(bot, config, throttle_secs)
                except TemporaryError as e:
                    logger.warning(
                        f"Strategy '{strategy_id}' temporary error: {e}, "
                        f"retrying in {RETRY_TIMEOUT}s..."
                    )
                    if inst._stop_event.wait(timeout=RETRY_TIMEOUT):
                        break
                except OperationalException:
                    tb = traceback.format_exc()
                    logger.exception(
                        f"Strategy '{strategy_id}' OperationalException, stopping..."
                    )
                    inst.error_message = tb
                    inst.status = StrategyStatus.ERROR
                    break
                except Exception:
                    tb = traceback.format_exc()
                    logger.exception(f"Strategy '{strategy_id}' unexpected error")
                    inst.error_message = tb
                    inst.status = StrategyStatus.ERROR
                    break

        except Exception as e:
            tb = traceback.format_exc()
            logger.exception(f"Strategy '{strategy_id}' failed to start: {e}")
            inst.error_message = str(e)
            inst.status = StrategyStatus.ERROR
            return
        finally:
            # Cleanup
            try:
                if inst.bot:
                    inst.bot.cleanup()
                    inst.bot = None
            except Exception:
                logger.exception(f"Strategy '{strategy_id}' cleanup error")

            if inst.status != StrategyStatus.ERROR:
                inst.status = StrategyStatus.STOPPED
            inst.stopped_at = datetime.now(timezone.utc)
            logger.info(f"Strategy thread '{strategy_id}' exited (status: {inst.status.value})")

    def _process_iteration(
        self, bot, config: dict, throttle_secs: float
    ) -> None:
        """Run one iteration of the trading loop."""
        start_time = time.time()
        bot.process()
        elapsed = time.time() - start_time

        # Calculate sleep time aligned to candle
        sleep_duration = max(throttle_secs - elapsed, 0.0)
        timeframe = config.get("timeframe")
        if timeframe:
            next_tf = timeframe_to_next_date(timeframe)
            next_tft = next_tf.timestamp() - time.time()
            next_tf_with_offset = next_tft + 1.0
            if next_tft < sleep_duration and sleep_duration < next_tf_with_offset:
                sleep_duration = next_tf_with_offset
            sleep_duration = min(sleep_duration, next_tf_with_offset)
            sleep_duration = max(sleep_duration, 0.0)

        if sleep_duration > 0:
            time.sleep(sleep_duration)

    def _build_strategy_config(
        self, strategy_config: dict[str, Any], strategy_id: str
    ) -> dict[str, Any]:
        """
        Build a complete Freqtrade config for a single strategy,
        merging the base engine config with strategy-specific settings.
        """
        # Exclude non-picklable objects (strategy_manager, api_server, etc.) from deepcopy
        skip_keys = {'strategy_manager', 'api_server', 'freqtradebot', 'rpc'}
        base_safe = {k: v for k, v in self._base_config.items() if k not in skip_keys}
        config = copy.deepcopy(base_safe)
        config.update(copy.deepcopy(strategy_config))

        # Ensure per-strategy database (separate SQLite for each)
        if "db_url" not in strategy_config:
            data_dir = config.get("user_data_dir", "user_data")
            config["db_url"] = f"sqlite:///{data_dir}/strategies/{strategy_id}/tradesv3.sqlite"

        # Ensure the strategy data directory exists
        import os
        data_dir = config.get("user_data_dir", "user_data")
        os.makedirs(f"{data_dir}/strategies/{strategy_id}", exist_ok=True)

        # Set internals
        config.setdefault("internals", {})
        config["internals"].setdefault("process_throttle_secs", PROCESS_THROTTLE_SECS)

        # Ensure runmode is set for trading
        from freqtrade.enums import RunMode
        if config.get("dry_run", True):
            config["runmode"] = RunMode.DRY_RUN
        else:
            config["runmode"] = RunMode.LIVE

        return config
