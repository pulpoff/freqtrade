import logging
import re

from fastapi import APIRouter, Depends, HTTPException

from freqtrade.data.history.datahandlers import get_datahandler
from freqtrade.enums import CandleType, TradingMode
from freqtrade.rpc.api_server.api_schemas import (
    AvailablePairs,
    ExchangeListResponse,
    FreqAIModelListResponse,
    HyperoptLossListResponse,
    StrategyListResponse,
    StrategyUploadRequest,
    StrategyUploadResponse,
)
from freqtrade.rpc.api_server.deps import get_config


logger = logging.getLogger(__name__)

# Private API, protected by authentication and webserver_mode dependency
router = APIRouter()


@router.get("/strategies", response_model=StrategyListResponse, tags=["Strategy"])
def list_strategies(config=Depends(get_config)):
    from freqtrade.resolvers.strategy_resolver import StrategyResolver

    strategies = StrategyResolver.search_all_objects(
        config, False, config.get("recursive_strategy_search", False)
    )
    strategies = sorted(strategies, key=lambda x: x["name"])

    return {"strategies": [x["name"] for x in strategies]}


@router.post("/strategies/upload", response_model=StrategyUploadResponse, tags=["Strategy"])
def upload_strategy(payload: StrategyUploadRequest, config=Depends(get_config)):
    """Upload a .py strategy file to the user_data/strategies directory."""
    from pathlib import Path

    code = payload.strategy
    name = payload.name

    # If no name provided, try to extract class name from code
    if not name:
        match = re.search(r"class\s+(\w+)\s*\(", code)
        if match:
            name = match.group(1)
        else:
            raise HTTPException(status_code=400, detail="Could not determine strategy name")

    # Sanitize filename - only allow alphanumeric and underscores
    safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid strategy name")

    # Write to strategies directory
    strategies_dir = Path(config.get("user_data_dir", "user_data")) / "strategies"
    strategies_dir.mkdir(parents=True, exist_ok=True)

    filepath = strategies_dir / f"{safe_name}.py"
    filepath.write_text(code, encoding="utf-8")

    logger.info(f"Strategy uploaded: {safe_name} -> {filepath}")
    return {"status": "ok", "name": safe_name}


@router.get("/exchanges", response_model=ExchangeListResponse, tags=[])
def list_exchanges(config=Depends(get_config)):
    from freqtrade.exchange import list_available_exchanges

    exchanges = list_available_exchanges(config)
    return {
        "exchanges": exchanges,
    }


@router.get("/hyperoptloss", response_model=HyperoptLossListResponse, tags=["Hyperopt"])
def list_hyperoptloss(
    config=Depends(get_config),
):
    import textwrap

    from freqtrade.resolvers.hyperopt_resolver import HyperOptLossResolver

    loss_functions = HyperOptLossResolver.search_all_objects(config, False)
    loss_functions = sorted(loss_functions, key=lambda x: x["name"])

    return {
        "loss_functions": [
            {
                "name": x["name"],
                "description": textwrap.dedent((x["class"].__doc__ or "").strip()),
            }
            for x in loss_functions
        ]
    }


@router.get("/freqaimodels", response_model=FreqAIModelListResponse, tags=["FreqAI"])
def list_freqaimodels(config=Depends(get_config)):
    from freqtrade.resolvers.freqaimodel_resolver import FreqaiModelResolver

    models = FreqaiModelResolver.search_all_objects(config, False)
    models = sorted(models, key=lambda x: x["name"])

    return {"freqaimodels": [x["name"] for x in models]}


@router.get(
    "/available_pairs", response_model=AvailablePairs, tags=["Candle data", "Download-data"]
)
def list_available_pairs(
    timeframe: str | None = None,
    stake_currency: str | None = None,
    candletype: CandleType | None = None,
    config=Depends(get_config),
):
    dh = get_datahandler(config["datadir"], config.get("dataformat_ohlcv"))
    trading_mode: TradingMode = config.get("trading_mode", TradingMode.SPOT)
    pair_interval = dh.ohlcv_get_available_data(config["datadir"], trading_mode)

    if timeframe:
        pair_interval = [pair for pair in pair_interval if pair[1] == timeframe]
    if stake_currency:
        pair_interval = [pair for pair in pair_interval if pair[0].endswith(stake_currency)]
    if candletype:
        pair_interval = [pair for pair in pair_interval if pair[2] == candletype]
    else:
        candle_type = CandleType.get_default(trading_mode)
        pair_interval = [pair for pair in pair_interval if pair[2] == candle_type]

    pair_interval = sorted(pair_interval, key=lambda x: x[0])

    pairs = list({x[0] for x in pair_interval})
    pairs.sort()
    result = {
        "length": len(pairs),
        "pairs": pairs,
        "pair_interval": pair_interval,
    }
    return result
