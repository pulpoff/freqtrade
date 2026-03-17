import logging
import time
from fastapi import APIRouter, Depends, HTTPException

from freqtrade.configuration import validate_config_consistency
from freqtrade.enums import CandleType
from freqtrade.rpc.api_server.api_pairlists import handleExchangePayload
from freqtrade.rpc.api_server.api_schemas import PairHistory, PairHistoryRequest, PairOHLCV
from freqtrade.rpc.api_server.deps import get_config, get_exchange, safe_deepcopy, verify_strategy
from freqtrade.rpc.rpc import RPC


logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/pair_history", response_model=PairHistory, tags=["Candle data"])
def pair_history(
    pair: str,
    timeframe: str,
    timerange: str,
    strategy: str,
    freqaimodel: str | None = None,
    config=Depends(get_config),
    exchange=Depends(get_exchange),
):
    verify_strategy(strategy)
    # The initial call to this endpoint can be slow, as it may need to initialize
    # the exchange class.
    config_loc = safe_deepcopy(config)
    config_loc.update(
        {
            "timeframe": timeframe,
            "strategy": strategy,
            "timerange": timerange,
            "freqaimodel": freqaimodel if freqaimodel else config_loc.get("freqaimodel"),
        }
    )
    validate_config_consistency(config_loc)
    try:
        return RPC._rpc_analysed_history_full(config_loc, pair, timeframe, exchange, None, False)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/pair_history", response_model=PairHistory, tags=["Candle data"])
def pair_history_filtered(payload: PairHistoryRequest, config=Depends(get_config)):
    verify_strategy(payload.strategy)
    # The initial call to this endpoint can be slow, as it may need to initialize
    # the exchange class.
    config_loc = safe_deepcopy(config)
    config_loc.update(
        {
            "timeframe": payload.timeframe,
            "strategy": payload.strategy,
            "timerange": payload.timerange,
            "freqaimodel": (
                payload.freqaimodel if payload.freqaimodel else config_loc.get("freqaimodel")
            ),
        }
    )
    handleExchangePayload(payload, config_loc)
    exchange = get_exchange(config_loc)

    validate_config_consistency(config_loc)

    try:
        return RPC._rpc_analysed_history_full(
            config_loc,
            payload.pair,
            payload.timeframe,
            exchange,
            payload.columns,
            payload.live_mode,
        )
    except Exception as e:
        logger.error(f"Error in pair_history_filtered: {type(e).__name__}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/pair_ohlcv", response_model=PairOHLCV, tags=["Candle data"])
def pair_ohlcv(
    pair: str,
    timeframe: str,
    limit: int = 500,
    config=Depends(get_config),
    exchange=Depends(get_exchange),
):
    """
    Fetch raw OHLCV data directly from the exchange.
    No strategy required — works in engine mode without any bot running.
    """
    try:
        # Calculate since_ms based on limit and timeframe
        tf_secs = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600,
            "8h": 28800, "12h": 43200, "1d": 86400, "1w": 604800,
        }
        secs = tf_secs.get(timeframe, 300)
        since_ms = int((time.time() - secs * limit) * 1000)

        candle_type = CandleType.get_default(config.get("trading_mode", "spot"))
        df = exchange.get_historic_ohlcv(
            pair=pair,
            timeframe=timeframe,
            since_ms=since_ms,
            candle_type=candle_type,
        )

        if df is None or df.empty:
            return {"pair": pair, "timeframe": timeframe, "columns": [], "data": [], "length": 0}

        columns = ["date", "open", "high", "low", "close", "volume"]
        data = []
        for _, row in df.iterrows():
            ts = int(row["date"].timestamp() * 1000)
            data.append([ts, row["open"], row["high"], row["low"], row["close"], row["volume"]])

        return {
            "pair": pair,
            "timeframe": timeframe,
            "columns": columns,
            "data": data,
            "length": len(data),
        }

    except Exception as e:
        logger.error(f"Error in pair_ohlcv: {type(e).__name__}: {e}")
        raise HTTPException(status_code=502, detail=str(e))
