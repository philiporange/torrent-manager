"""
Torrent Manager API Server

FastAPI server with secure session-based authentication using HTTP-only cookies
with sliding expiration and remember-me functionality.

The server includes automatic port availability checking with retry logic to handle
graceful restarts when the previous instance is still shutting down.

Usage:
    python server.py                    # Run on default port 8000
    python server.py --port 8080        # Run on custom port
    python server.py --reload           # Run with auto-reload (development)
"""

import argparse
import socket
import sys
import time
import uvicorn
from .api import app
from .logger import logger
from .config import Config


def _check_port_available(host: str, port: int, max_retries: int = 5, retry_delay: float = 2.0) -> bool:
    """
    Check if a port is available for binding, with retry logic.

    Args:
        host: Host address to check
        port: Port number to check
        max_retries: Maximum number of retries before giving up
        retry_delay: Delay in seconds between retries

    Returns:
        True if port is available, False otherwise
    """
    for attempt in range(max_retries):
        try:
            # Try to bind to the port to check availability
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            sock.close()
            return True
        except OSError as e:
            if e.errno == 98:  # Address already in use
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Port {port} is already in use. Waiting {retry_delay}s for previous "
                        f"instance to shut down (attempt {attempt + 1}/{max_retries})..."
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error(
                        f"Port {port} is still in use after {max_retries} attempts. "
                        f"Please ensure no other instance is running."
                    )
                    return False
            else:
                # Other socket error
                logger.error(f"Error checking port {port}: {e}")
                return False

    return False


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

    # Check if port is available before starting
    if not _check_port_available(host, port):
        logger.error(f"Cannot start server: port {port} is not available")
        sys.exit(1)

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
