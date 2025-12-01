from fastapi import APIRouter, Response
from fastapi.responses import FileResponse
from torrent_manager.config import Config

router = APIRouter(tags=["pages"])

@router.get("/login")
async def login_page():
    """Serve the login page."""
    return FileResponse("torrent_manager/static/login.html", media_type="text/html")


@router.get("/manage-servers")
async def servers_page():
    """Serve the server management page."""
    return FileResponse("torrent_manager/static/servers.html", media_type="text/html")


@router.get("/manage-api-keys")
async def api_keys_page():
    """Serve the API key management page."""
    return FileResponse("torrent_manager/static/api_keys.html", media_type="text/html")


@router.get("/")
async def root():
    """Serve the frontend index.html."""
    return FileResponse("torrent_manager/static/index.html", media_type="text/html")


@router.get("/config.js")
async def config_js():
    """Serve frontend configuration as JavaScript."""
    config = Config()
    config_js_content = f"""
// API Configuration (generated)
window.API_CONFIG = {{
    API_BASE_URL: '{config.API_BASE_URL}',
    API_HOST: '{config.API_HOST}',
    API_PORT: {config.API_PORT},
    API_BASE_PATH: '{config.API_BASE_PATH}'
}};
"""
    return Response(content=config_js_content, media_type="application/javascript")


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}
