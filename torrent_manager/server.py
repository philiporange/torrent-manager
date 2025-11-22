"""
Torrent Manager API Server

FastAPI server with secure session-based authentication using HTTP-only cookies
with sliding expiration and remember-me functionality.

Usage:
    python server.py                    # Run on default port 8000
    python server.py --port 8080        # Run on custom port
    python server.py --reload           # Run with auto-reload (development)
"""

import argparse
import uvicorn
from .api import app
from .logger import logger
from .config import Config


def main():
    parser = argparse.ArgumentParser(
        description="Torrent Manager API Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python server.py                    Run on default port 8144 (all interfaces)
  python server.py --port 8080        Run on custom port
  python server.py --reload           Run with auto-reload (development)
  python server.py --host 127.0.0.1   Listen on localhost only

Authentication:
  The server uses secure HTTP-only session cookies with sliding expiration.

  Endpoints:
    POST /auth/register    Register new user
    POST /auth/login       Login and create session
    POST /auth/logout      Logout and destroy session
    GET  /auth/me          Get current user info
    GET  /health           Health check
    GET  /docs             API documentation

Security Features:
  - Server-set, HTTP-only secure session cookies
  - Sliding expiration (resets on each user interaction)
  - ITP-safe sliding window (< 7 days)
  - Remember-me tokens for longer-lived authentication
  - Cookie format: Set-Cookie: session=<opaque>; Path=/; Secure; HttpOnly; SameSite=Lax
        """
    )

    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8144,
        help="Port to bind to (default: 8144)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (development mode)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1)"
    )

    args = parser.parse_args()

    # Load configuration
    config = Config()

    # Use command line args if provided, otherwise use environment config
    host = args.host if args.host != "0.0.0.0" else config.HOST
    port = args.port if args.port != 8144 else config.PORT

    logger.info(f"Starting Torrent Manager API on {host}:{port}")
    logger.info(f"API Base URL: {config.API_BASE_URL}")
    logger.info(f"Documentation available at http://{host}:{port}/docs")

    uvicorn.run(
        "torrent_manager.api:app",
        host=host,
        port=port,
        reload=args.reload,
        workers=args.workers
    )


if __name__ == "__main__":
    main()
