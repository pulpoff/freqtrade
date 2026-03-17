from pathlib import Path

from fastapi import APIRouter
from fastapi.exceptions import HTTPException
from starlette.responses import FileResponse


router_ui = APIRouter(include_in_schema=False, tags=["Web UI"])

# BotCrypto UI directory (default GUI)
_botcrypto_dir = Path(__file__).parents[3] / "botcrypto"
# Legacy FreqUI directory
_frequi_dir = Path(__file__).parent / "ui/installed/"


def _get_ui_base() -> Path:
    """
    Returns the UI base directory.
    BotCrypto is the default GUI. Falls back to FreqUI if botcrypto is not found.
    """
    if (_botcrypto_dir / "index.html").is_file():
        return _botcrypto_dir
    return _frequi_dir


@router_ui.get("/favicon.ico")
async def favicon():
    return FileResponse(str(Path(__file__).parent / "ui/favicon.ico"))


@router_ui.get("/fallback_file.html")
async def fallback():
    return FileResponse(str(Path(__file__).parent / "ui/fallback_file.html"))


@router_ui.get("/ui_version")
async def ui_version():
    from freqtrade.commands.deploy_ui import read_ui_version

    uibase = _get_ui_base()
    if uibase == _botcrypto_dir:
        return {"version": "botcrypto-1.0.0"}

    version = read_ui_version(_frequi_dir)
    return {
        "version": version if version else "not_installed",
    }


@router_ui.get("/{rest_of_path:path}")
async def index_html(rest_of_path: str):
    """
    Serve BotCrypto web UI (default) or FreqUI as fallback.
    Emulates path fallback to index.html for SPA routing.
    """
    if rest_of_path.startswith("api") or rest_of_path.startswith("."):
        raise HTTPException(status_code=404, detail="Not Found")

    uibase = _get_ui_base()
    filename = uibase / rest_of_path

    # Security: prevent directory traversal
    uibase = (Path(__file__).parent / "ui/installed/").resolve()
    filename = (uibase / rest_of_path).resolve()
    # It's security relevant to check "relative_to".
    # Without this, Directory-traversal is possible.
    media_type: str | None = None
    if filename.suffix == ".js":
        media_type = "application/javascript"
    elif filename.suffix == ".css":
        media_type = "text/css"

    if filename.is_file() and filename.is_relative_to(uibase):
        return FileResponse(str(filename), media_type=media_type)

    index_file = uibase / "index.html"
    if not index_file.is_file():
        return FileResponse(str(Path(__file__).parent / "ui/fallback_file.html"))
    # Fall back to index.html for SPA routing
    return FileResponse(str(index_file))
