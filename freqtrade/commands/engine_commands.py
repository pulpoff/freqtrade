"""
BotCrypto Engine startup command.

Starts the API server + GUI without requiring a strategy or exchange config.
Strategies are managed at runtime via the API/GUI.
"""

import logging
import os
import secrets
import signal
from pathlib import Path
from typing import Any

from freqtrade.enums import RunMode


logger = logging.getLogger(__name__)


def _load_env_config() -> dict[str, Any]:
    """
    Load engine configuration from .env file and environment variables.
    Returns a minimal Freqtrade config suitable for running the API server.
    """
    # Try to load .env file
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    api_host = os.environ.get("BC_API_HOST", "0.0.0.0")
    api_port = int(os.environ.get("BC_API_PORT", "8080"))
    api_username = os.environ.get("BC_API_USERNAME", "freqtrader")
    api_password = os.environ.get("BC_API_PASSWORD", "")
    jwt_secret = os.environ.get("BC_JWT_SECRET", secrets.token_hex(32))
    cors_origins = os.environ.get("BC_CORS_ORIGINS", "").split(",")
    cors_origins = [o.strip() for o in cors_origins if o.strip()]
    data_dir = os.environ.get("BC_DATA_DIR", "user_data")
    log_level = os.environ.get("BC_LOG_LEVEL", "INFO")

    if not api_password:
        logger.warning(
            "BC_API_PASSWORD not set! Set it in .env or environment. "
            "Using empty password (insecure)."
        )

    config: dict[str, Any] = {
        "runmode": RunMode.WEBSERVER,
        "dry_run": True,
        "trading_mode": "spot",
        "stake_currency": "USDT",
        "user_data_dir": data_dir,
        "verbosity": 0,
        "api_server": {
            "enabled": True,
            "listen_ip_address": api_host,
            "listen_port": api_port,
            "username": api_username,
            "password": api_password,
            "jwt_secret_key": jwt_secret,
            "CORS_origins": cors_origins,
            "verbosity": "error",
        },
        # Minimal exchange config (not used until a strategy is started)
        "exchange": {
            "name": "binance",
            "key": "",
            "secret": "",
            "pair_whitelist": [],
            "pair_blacklist": [],
        },
        "pairlists": [{"method": "StaticPairList"}],
        # Engine mode flag
        "engine_mode": True,
    }

    return config


def start_engine(args: dict[str, Any]) -> int:
    """
    Start the BotCrypto engine — API server + GUI only.
    No strategy or exchange config required.
    Strategies are managed at runtime via the GUI/API.
    """
    from freqtrade.configuration import setup_logging
    from freqtrade.rpc.api_server import ApiServer
    from freqtrade.strategy_manager import StrategyManager

    def term_handler(signum, frame):
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, term_handler)

    # Load config from .env / environment
    config = _load_env_config()

    # Merge any config file if provided via --config
    if args.get("config"):
        from freqtrade.configuration import Configuration
        file_config = Configuration(args, RunMode.WEBSERVER).get_config()
        # Keep our api_server and engine_mode settings
        api_server = config["api_server"]
        engine_mode = config["engine_mode"]
        config.update(file_config)
        config["api_server"] = api_server
        config["engine_mode"] = engine_mode
        config["runmode"] = RunMode.WEBSERVER

    # Setup logging
    log_level = os.environ.get("BC_LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting BotCrypto Engine...")
    logger.info(
        f"API Server: {config['api_server']['listen_ip_address']}"
        f":{config['api_server']['listen_port']}"
    )

    # Create strategy manager and attach to config for API access
    strategy_manager = StrategyManager(config)
    config["strategy_manager"] = strategy_manager

    try:
        # Start the API server (blocks in standalone mode)
        api_server = ApiServer(config, standalone=True)
    except KeyboardInterrupt:
        logger.info("Engine shutdown requested")
    finally:
        # Stop all running strategies
        logger.info("Stopping all strategies...")
        strategy_manager.stop_all()
        logger.info("BotCrypto Engine stopped.")

    return 0
