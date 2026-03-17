"""
BotCrypto Engine startup command.

Starts the API server + GUI with exchange access from config.json.
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


def _load_env_overrides() -> dict[str, Any]:
    """
    Load .env file and return API server overrides from BC_* environment variables.
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

    overrides: dict[str, Any] = {}

    # API server overrides from environment
    api_host = os.environ.get("BC_API_HOST")
    api_port = os.environ.get("BC_API_PORT")
    api_username = os.environ.get("BC_API_USERNAME")
    api_password = os.environ.get("BC_API_PASSWORD")
    jwt_secret = os.environ.get("BC_JWT_SECRET")
    cors_origins = os.environ.get("BC_CORS_ORIGINS")
    log_level = os.environ.get("BC_LOG_LEVEL")

    api_overrides: dict[str, Any] = {}
    if api_host is not None:
        api_overrides["listen_ip_address"] = api_host
    if api_port is not None:
        api_overrides["listen_port"] = int(api_port)
    if api_username is not None:
        api_overrides["username"] = api_username
    if api_password is not None:
        api_overrides["password"] = api_password
    if jwt_secret is not None:
        api_overrides["jwt_secret_key"] = jwt_secret
    if cors_origins is not None:
        api_overrides["CORS_origins"] = [o.strip() for o in cors_origins.split(",") if o.strip()]

    if api_overrides:
        overrides["api_server"] = api_overrides
    if log_level is not None:
        overrides["log_level"] = log_level

    return overrides


def start_engine(args: dict[str, Any]) -> int:
    """
    Start the BotCrypto engine — API server + GUI.
    Loads exchange config from config.json, no strategy required.
    Strategies are managed at runtime via the GUI/API.
    """
    from freqtrade.configuration import Configuration
    from freqtrade.rpc.api_server import ApiServer
    from freqtrade.strategy_manager import StrategyManager

    def term_handler(signum, frame):
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, term_handler)

    # Load .env overrides first (populates os.environ for BC_* vars)
    env_overrides = _load_env_overrides()

    # Load config.json via standard Configuration (handles user_data/config.json auto-discovery)
    config = Configuration(args, RunMode.WEBSERVER).get_config()

    # Apply .env overrides on top of config.json
    if "api_server" in env_overrides:
        if "api_server" not in config:
            config["api_server"] = {}
        config["api_server"].update(env_overrides["api_server"])

    # Ensure API server is enabled with sensible defaults
    api_cfg = config.setdefault("api_server", {})
    api_cfg.setdefault("enabled", True)
    api_cfg.setdefault("listen_ip_address", "0.0.0.0")
    api_cfg.setdefault("listen_port", 8080)
    api_cfg.setdefault("username", "freqtrader")
    api_cfg.setdefault("password", "")
    api_cfg.setdefault("jwt_secret_key", secrets.token_hex(32))
    api_cfg.setdefault("verbosity", "error")

    if not api_cfg.get("password"):
        logger.warning(
            "API password not set! Set it in config.json or BC_API_PASSWORD env var."
        )

    # Set engine mode flags
    config["engine_mode"] = True
    config["runmode"] = RunMode.WEBSERVER

    # Setup logging
    log_level = env_overrides.get("log_level", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting BotCrypto Engine...")
    logger.info(
        f"API Server: {config['api_server']['listen_ip_address']}"
        f":{config['api_server']['listen_port']}"
    )
    logger.info(f"Exchange: {config.get('exchange', {}).get('name', 'not configured')}")

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
