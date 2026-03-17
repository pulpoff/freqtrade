"""
API endpoints for multi-strategy management.

These endpoints allow the BotCrypto GUI to:
- List all managed strategies and their status
- Add/remove strategy configurations
- Start/stop individual strategies
- Get per-strategy trade info and stats
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from freqtrade.rpc.api_server.api_auth import http_basic_or_jwt_token
from freqtrade.rpc.api_server.deps import get_config


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Strategy Manager"])


# --- Pydantic models ---

class StrategyConfig(BaseModel):
    """Configuration for a new strategy to be managed."""
    strategy_id: str
    strategy: str  # strategy class name
    exchange: dict[str, Any]  # {name, key, secret, pair_whitelist, pair_blacklist}
    stake_currency: str = "USDT"
    stake_amount: Any = "unlimited"  # can be float or "unlimited"
    max_open_trades: int = 3
    dry_run: bool = True
    dry_run_wallet: float = 1000
    trading_mode: str = "spot"
    timeframe: str = "5m"
    stoploss: float = -0.10
    trailing_stop: bool = False
    trailing_stop_positive: float | None = None
    minimal_roi: dict[str, float] = {"0": 0.04, "20": 0.02, "40": 0.01, "60": 0}
    # Additional config passthrough
    extra_config: dict[str, Any] = {}
    # Auto-start on engine launch
    auto_start: bool = False


class StrategyAction(BaseModel):
    """Action to perform on a strategy."""
    strategy_id: str


class StrategyResponse(BaseModel):
    """Response for a single strategy."""
    strategy_id: str
    strategy_name: str
    exchange: str
    trading_mode: str
    dry_run: bool
    stake_currency: str
    pairs: list[str]
    status: str
    error: str | None = None
    started_at: str | None = None
    stopped_at: str | None = None
    bot_state: str | None = None


# --- Helper ---

def _get_strategy_manager(config=Depends(get_config)):
    """Get the StrategyManager from config."""
    sm = config.get("strategy_manager")
    if sm is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="Strategy manager not available. Start with 'freqtrade engine'."
        )
    return sm


# --- Endpoints ---

@router.get("/strategies", response_model=list[StrategyResponse])
def list_strategies(sm=Depends(_get_strategy_manager)):
    """List all managed strategies and their current status."""
    return sm.list_strategies()


@router.get("/strategies/{strategy_id}")
def get_strategy(strategy_id: str, sm=Depends(_get_strategy_manager)):
    """Get details of a specific strategy."""
    inst = sm.get_strategy(strategy_id)
    if inst is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")
    return inst.to_dict()


@router.post("/strategies")
def add_strategy(body: StrategyConfig, sm=Depends(_get_strategy_manager)):
    """Add a new strategy configuration."""
    config = {
        "strategy": body.strategy,
        "exchange": body.exchange,
        "stake_currency": body.stake_currency,
        "stake_amount": body.stake_amount,
        "max_open_trades": body.max_open_trades,
        "dry_run": body.dry_run,
        "dry_run_wallet": body.dry_run_wallet,
        "trading_mode": body.trading_mode,
        "timeframe": body.timeframe,
        "stoploss": body.stoploss,
        "trailing_stop": body.trailing_stop,
        "minimal_roi": body.minimal_roi,
        "auto_start": body.auto_start,
        **body.extra_config,
    }
    if body.trailing_stop_positive is not None:
        config["trailing_stop_positive"] = body.trailing_stop_positive

    inst = sm.add_strategy(body.strategy_id, config)
    return {"status": "added", **inst.to_dict()}


@router.delete("/strategies/{strategy_id}")
def remove_strategy(strategy_id: str, sm=Depends(_get_strategy_manager)):
    """Remove a strategy (must be stopped first)."""
    sm.remove_strategy(strategy_id)
    return {"status": "removed", "strategy_id": strategy_id}


@router.post("/strategies/{strategy_id}/start")
def start_strategy(strategy_id: str, sm=Depends(_get_strategy_manager)):
    """Start a strategy in a new thread."""
    inst = sm.start_strategy(strategy_id)
    return {"status": "starting", **inst.to_dict()}


@router.post("/strategies/{strategy_id}/stop")
def stop_strategy(strategy_id: str, sm=Depends(_get_strategy_manager)):
    """Stop a running strategy."""
    inst = sm.stop_strategy(strategy_id)
    return {"status": "stopping", **inst.to_dict()}


@router.get("/strategies/{strategy_id}/trades")
def get_strategy_trades(strategy_id: str, sm=Depends(_get_strategy_manager)):
    """Get open trades for a specific strategy."""
    bot = sm.get_strategy_bot(strategy_id)
    if bot is None:
        return {"trades": [], "trades_count": 0}

    try:
        from freqtrade.persistence import Trade
        trades = Trade.get_trades_proxy(is_open=True)
        open_trades = []
        for t in trades:
            open_trades.append({
                "trade_id": t.id,
                "pair": t.pair,
                "stake_amount": t.stake_amount,
                "amount": t.amount,
                "open_rate": t.open_rate,
                "current_rate": t.close_rate or t.open_rate,
                "profit_pct": t.calc_profit_ratio(t.close_rate) if t.close_rate else 0,
                "open_date": t.open_date_utc.isoformat() if t.open_date_utc else None,
            })
        return {"trades": open_trades, "trades_count": len(open_trades)}
    except Exception as e:
        logger.error(f"Error getting trades for '{strategy_id}': {e}")
        return {"trades": [], "trades_count": 0, "error": str(e)}


@router.get("/strategies/{strategy_id}/profit")
def get_strategy_profit(strategy_id: str, sm=Depends(_get_strategy_manager)):
    """Get profit summary for a specific strategy."""
    bot = sm.get_strategy_bot(strategy_id)
    if bot is None:
        return {"profit_all_coin": 0, "profit_all_percent": 0, "trade_count": 0}

    try:
        from freqtrade.rpc.rpc import RPC
        rpc = RPC(bot)
        return rpc._rpc_trade_statistics(bot.config["stake_currency"])
    except Exception as e:
        logger.error(f"Error getting profit for '{strategy_id}': {e}")
        return {"profit_all_coin": 0, "profit_all_percent": 0, "trade_count": 0, "error": str(e)}


@router.get("/engine/status")
def engine_status(config=Depends(get_config)):
    """Get engine-level status information."""
    sm = config.get("strategy_manager")
    strategies = sm.list_strategies() if sm else []

    running = sum(1 for s in strategies if s["status"] == "running")
    stopped = sum(1 for s in strategies if s["status"] == "stopped")
    errored = sum(1 for s in strategies if s["status"] == "error")

    return {
        "engine_mode": config.get("engine_mode", False),
        "total_strategies": len(strategies),
        "running": running,
        "stopped": stopped,
        "errored": errored,
        "strategies": strategies,
    }
