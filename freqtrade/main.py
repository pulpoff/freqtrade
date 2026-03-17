#!/usr/bin/env python3
"""
Main Freqtrade bot script.
Read the documentation to know what cli arguments you need.
"""

import logging
import sys
from typing import Any


# check min. python version
if sys.version_info < (3, 11):  # pragma: no cover  # noqa: UP036
    sys.exit("Freqtrade requires Python version >= 3.11")

from freqtrade import __version__
from freqtrade.commands import Arguments
from freqtrade.constants import DOCS_LINK
from freqtrade.exceptions import ConfigurationError, FreqtradeException, OperationalException
from freqtrade.loggers import setup_logging_pre
from freqtrade.system import (
    asyncio_setup,
    gc_set_threshold,
    print_version_info,
    set_mp_start_method,
)


logger = logging.getLogger("freqtrade")


def main(sysargv: list[str] | None = None) -> None:
    """
    This function will initiate the bot and start the trading loop.
    :return: None
    """

    return_code: Any = 1
    try:
        setup_logging_pre()
        asyncio_setup()
        arguments = Arguments(sysargv)
        args = arguments.get_parsed_arg()

        # Call subcommand.
        if args.get("version") or args.get("version_main"):
            print_version_info()
            return_code = 0
        elif "func" in args:
            logger.info(f"freqtrade {__version__}")
            gc_set_threshold()
            set_mp_start_method()
            return_code = args["func"](args)
        else:
            # No subcommand was issued — default to engine mode
            logger.info(f"freqtrade {__version__}")
            logger.info("No subcommand specified, starting in engine mode...")
            gc_set_threshold()
            set_mp_start_method()

            # Populate args as if "engine" subcommand was used
            # (top-level parser lacks config/user_data_dir from _common_parser)
            from pathlib import Path

            from freqtrade.commands import start_engine
            from freqtrade.constants import DEFAULT_CONFIG

            if "config" not in args or args.get("config") is None:
                user_dir = args.get("user_data_dir", "user_data")
                cfgfile = Path(user_dir) / DEFAULT_CONFIG
                if cfgfile.is_file():
                    args["config"] = [str(cfgfile)]
                elif (Path.cwd() / DEFAULT_CONFIG).is_file():
                    args["config"] = [DEFAULT_CONFIG]

            return_code = start_engine(args)

    except SystemExit as e:  # pragma: no cover
        return_code = e
    except KeyboardInterrupt:
        logger.info("SIGINT received, aborting ...")
        return_code = 0
    except ConfigurationError as e:
        logger.error(
            f"Configuration error: {e}\n"
            f"Please make sure to review the documentation at {DOCS_LINK}."
        )
    except FreqtradeException as e:
        logger.error(str(e))
        return_code = 2
    except Exception:
        logger.exception("Fatal exception!")
    finally:
        sys.exit(return_code)


if __name__ == "__main__":  # pragma: no cover
    main()
