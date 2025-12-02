"""
Command-line interface for Torrent Manager.

Provides terminal access to all API functionality including:
- User authentication and API key management
- Server configuration (add, list, update, remove, test)
- Torrent operations (add, list, start, stop, remove)
- File browsing and downloads

Usage:
    torrent-manager login <username> <password>
    torrent-manager servers
    torrent-manager list
    torrent-manager add <magnet/url/file> --server <id>
    torrent-manager files <info_hash>
    torrent-manager download <server_id> <path>
"""

import argparse
import sys
import json
import os
import pickle
from typing import Optional
from pathlib import Path

from .client import TorrentManagerClient
from .config import Config

SESSION_FILE = Path.home() / ".torrent_manager_session"


def save_session(client: TorrentManagerClient):
    """Save the session cookies to a file."""
    with open(SESSION_FILE, "wb") as f:
        pickle.dump(client.session.cookies, f)


def load_session(client: TorrentManagerClient):
    """Load session cookies from a file if it exists."""
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, "rb") as f:
                client.session.cookies.update(pickle.load(f))
        except Exception:
            pass


def clear_session():
    """Remove the saved session file."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def format_bytes(size):
    """Format bytes as human-readable string."""
    if size is None:
        return "N/A"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def main():
    parser = argparse.ArgumentParser(
        description="Torrent Manager CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s login myuser mypassword
  %(prog)s servers
  %(prog)s add-server "My Server" rtorrent 192.168.1.10 80
  %(prog)s list --server abc123
  %(prog)s add magnet:?xt=... --server abc123
  %(prog)s files <info_hash>
  %(prog)s browse abc123 /downloads
  %(prog)s download abc123 /downloads/file.zip
"""
    )
    parser.add_argument("--url", default="http://localhost:8144", help="API URL")
    parser.add_argument("--api-key", help="API Key for authentication")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # -------------------------------------------------------------------------
    # Auth Commands
    # -------------------------------------------------------------------------

    login_parser = subparsers.add_parser("login", help="Login to the server")
    login_parser.add_argument("username", help="Username")
    login_parser.add_argument("password", help="Password")

    subparsers.add_parser("logout", help="Logout and clear session")

    reg_parser = subparsers.add_parser("register", help="Register a new user")
    reg_parser.add_argument("username", help="Username")
    reg_parser.add_argument("password", help="Password")

    subparsers.add_parser("whoami", help="Show current user info")

    # -------------------------------------------------------------------------
    # API Key Commands
    # -------------------------------------------------------------------------

    key_parser = subparsers.add_parser("create-key", help="Create an API key")
    key_parser.add_argument("name", help="Key name/description")
    key_parser.add_argument("--days", type=int, help="Expiration in days")

    subparsers.add_parser("list-keys", help="List your API keys")

    revoke_parser = subparsers.add_parser("revoke-key", help="Revoke an API key")
    revoke_parser.add_argument("prefix", help="Key prefix (first 8 characters)")

    # -------------------------------------------------------------------------
    # Server Commands
    # -------------------------------------------------------------------------

    subparsers.add_parser("servers", help="List all configured servers")

    add_server_parser = subparsers.add_parser("add-server", help="Add a new server")
    add_server_parser.add_argument("name", help="Display name for the server")
    add_server_parser.add_argument("type", choices=["rtorrent", "transmission"],
                                   help="Server type")
    add_server_parser.add_argument("host", help="Server hostname or IP")
    add_server_parser.add_argument("port", type=int, help="RPC port")
    add_server_parser.add_argument("--username", help="RPC username")
    add_server_parser.add_argument("--password", help="RPC password")
    add_server_parser.add_argument("--rpc-path", help="RPC path (e.g., /RPC2)")
    add_server_parser.add_argument("--ssl", action="store_true", help="Use HTTPS")
    add_server_parser.add_argument("--http-host", help="HTTP download host")
    add_server_parser.add_argument("--http-port", type=int, help="HTTP download port")
    add_server_parser.add_argument("--http-path", help="HTTP base path")
    add_server_parser.add_argument("--http-username", help="HTTP auth username")
    add_server_parser.add_argument("--http-password", help="HTTP auth password")
    add_server_parser.add_argument("--http-ssl", action="store_true", help="HTTP uses HTTPS")

    server_parser = subparsers.add_parser("server", help="Show server details")
    server_parser.add_argument("server_id", help="Server ID")

    update_server_parser = subparsers.add_parser("update-server", help="Update a server")
    update_server_parser.add_argument("server_id", help="Server ID")
    update_server_parser.add_argument("--name", help="New name")
    update_server_parser.add_argument("--host", help="New host")
    update_server_parser.add_argument("--port", type=int, help="New port")
    update_server_parser.add_argument("--username", help="New username")
    update_server_parser.add_argument("--password", help="New password")
    update_server_parser.add_argument("--rpc-path", help="New RPC path")
    update_server_parser.add_argument("--ssl", dest="use_ssl", action="store_true",
                                      default=None, help="Enable SSL")
    update_server_parser.add_argument("--no-ssl", dest="use_ssl", action="store_false",
                                      help="Disable SSL")
    update_server_parser.add_argument("--enable", dest="enabled", action="store_true",
                                      default=None, help="Enable server")
    update_server_parser.add_argument("--disable", dest="enabled", action="store_false",
                                      help="Disable server")
    update_server_parser.add_argument("--http-host", help="HTTP download host")
    update_server_parser.add_argument("--http-port", type=int, help="HTTP download port")
    update_server_parser.add_argument("--http-path", help="HTTP base path")
    update_server_parser.add_argument("--http-username", help="HTTP auth username")
    update_server_parser.add_argument("--http-password", help="HTTP auth password")
    update_server_parser.add_argument("--http-ssl", dest="http_use_ssl", action="store_true",
                                      default=None, help="HTTP uses HTTPS")
    update_server_parser.add_argument("--no-http-ssl", dest="http_use_ssl", action="store_false",
                                      help="HTTP doesn't use HTTPS")

    rm_server_parser = subparsers.add_parser("remove-server", help="Remove a server")
    rm_server_parser.add_argument("server_id", help="Server ID")

    test_server_parser = subparsers.add_parser("test-server", help="Test server connection")
    test_server_parser.add_argument("server_id", help="Server ID")

    # -------------------------------------------------------------------------
    # Torrent Commands
    # -------------------------------------------------------------------------

    list_parser = subparsers.add_parser("list", help="List all torrents")
    list_parser.add_argument("--server", dest="server_id", help="Filter by server ID")

    add_parser = subparsers.add_parser("add", help="Add a torrent")
    add_parser.add_argument("uri", help="Magnet URI, HTTP URL, or file path")
    add_parser.add_argument("--server", dest="server_id", required=True,
                           help="Server ID to add torrent to")
    add_parser.add_argument("--no-start", action="store_true",
                           help="Don't start immediately")

    info_parser = subparsers.add_parser("info", help="Show torrent details")
    info_parser.add_argument("info_hash", help="Torrent info hash")
    info_parser.add_argument("--server", dest="server_id", help="Server ID (optional)")

    start_parser = subparsers.add_parser("start", help="Start a torrent")
    start_parser.add_argument("info_hash", help="Torrent info hash")
    start_parser.add_argument("--server", dest="server_id", help="Server ID (optional)")

    stop_parser = subparsers.add_parser("stop", help="Stop a torrent")
    stop_parser.add_argument("info_hash", help="Torrent info hash")
    stop_parser.add_argument("--server", dest="server_id", help="Server ID (optional)")

    rm_parser = subparsers.add_parser("remove", help="Remove a torrent")
    rm_parser.add_argument("info_hash", help="Torrent info hash")
    rm_parser.add_argument("--server", dest="server_id", help="Server ID (optional)")

    # -------------------------------------------------------------------------
    # File Commands
    # -------------------------------------------------------------------------

    files_parser = subparsers.add_parser("files", help="List files in a torrent")
    files_parser.add_argument("info_hash", help="Torrent info hash")
    files_parser.add_argument("--server", dest="server_id", help="Server ID (optional)")

    browse_parser = subparsers.add_parser("browse", help="Browse server files")
    browse_parser.add_argument("server_id", help="Server ID")
    browse_parser.add_argument("path", nargs="?", default="",
                              help="Path to browse (default: root)")

    download_parser = subparsers.add_parser("download", help="Download a file from server")
    download_parser.add_argument("server_id", help="Server ID")
    download_parser.add_argument("file_path", help="Path to file on server")
    download_parser.add_argument("-o", "--output", help="Output file path")

    # -------------------------------------------------------------------------
    # Parse and Execute
    # -------------------------------------------------------------------------

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    client = TorrentManagerClient(base_url=args.url, api_key=args.api_key)

    # Load session unless we are providing an API key
    if not args.api_key:
        load_session(client)

    try:
        # ---------------------------------------------------------------------
        # Auth Commands
        # ---------------------------------------------------------------------

        if args.command == "login":
            res = client.login(args.username, args.password, remember_me=True)
            save_session(client)
            print(f"Logged in as {res['username']}")

        elif args.command == "logout":
            try:
                client.logout()
            except Exception:
                pass  # May fail if already logged out
            clear_session()
            print("Logged out")

        elif args.command == "register":
            res = client.register(args.username, args.password)
            print(f"Registered user {res['username']}")

        elif args.command == "whoami":
            res = client.get_me()
            print(json.dumps(res, indent=2))

        # ---------------------------------------------------------------------
        # API Key Commands
        # ---------------------------------------------------------------------

        elif args.command == "create-key":
            res = client.create_api_key(args.name, args.days)
            print(f"Created API Key: {res['api_key']}")
            print("SAVE THIS KEY! It will not be shown again.")

        elif args.command == "list-keys":
            res = client.list_api_keys()
            if not res.get("api_keys"):
                print("No API keys found.")
            else:
                print(f"{'PREFIX':<10} {'NAME':<20} {'CREATED':<20} {'EXPIRES':<20} {'REVOKED'}")
                print("-" * 80)
                for key in res["api_keys"]:
                    prefix = key.get("api_key_id", "")[:8]
                    name = key.get("name", "")[:20]
                    created = key.get("created_at", "")[:19]
                    expires = key.get("expires_at", "Never")
                    if expires:
                        expires = expires[:19]
                    revoked = "Yes" if key.get("revoked") else "No"
                    print(f"{prefix:<10} {name:<20} {created:<20} {expires:<20} {revoked}")

        elif args.command == "revoke-key":
            res = client.revoke_api_key(args.prefix)
            print(res.get("message", "API key revoked"))

        # ---------------------------------------------------------------------
        # Server Commands
        # ---------------------------------------------------------------------

        elif args.command == "servers":
            servers = client.list_servers()
            if not servers:
                print("No servers configured.")
            else:
                print(f"{'ID':<24} {'NAME':<20} {'TYPE':<12} {'HOST':<20} {'ENABLED'}")
                print("-" * 85)
                for s in servers:
                    sid = s.get("id", "")[:24]
                    name = s.get("name", "")[:20]
                    stype = s.get("server_type", "")[:12]
                    host = f"{s.get('host', '')}:{s.get('port', '')}"[:20]
                    enabled = "Yes" if s.get("enabled") else "No"
                    print(f"{sid:<24} {name:<20} {stype:<12} {host:<20} {enabled}")

        elif args.command == "add-server":
            res = client.add_server(
                name=args.name,
                server_type=args.type,
                host=args.host,
                port=args.port,
                username=args.username,
                password=args.password,
                rpc_path=args.rpc_path,
                use_ssl=args.ssl,
                http_host=args.http_host,
                http_port=args.http_port,
                http_path=args.http_path,
                http_username=args.http_username,
                http_password=args.http_password,
                http_use_ssl=args.http_ssl
            )
            print(f"Added server: {res['name']} (ID: {res['id']})")

        elif args.command == "server":
            res = client.get_server(args.server_id)
            print(json.dumps(res, indent=2))

        elif args.command == "update-server":
            res = client.update_server(
                server_id=args.server_id,
                name=args.name,
                host=args.host,
                port=args.port,
                username=args.username,
                password=args.password,
                rpc_path=args.rpc_path,
                use_ssl=args.use_ssl,
                enabled=args.enabled,
                http_host=args.http_host,
                http_port=args.http_port,
                http_path=args.http_path,
                http_username=args.http_username,
                http_password=args.http_password,
                http_use_ssl=args.http_use_ssl
            )
            print(f"Updated server: {res['name']}")

        elif args.command == "remove-server":
            res = client.delete_server(args.server_id)
            print(res.get("message", "Server removed"))

        elif args.command == "test-server":
            res = client.test_server(args.server_id)
            print(f"{res.get('status', 'unknown').upper()}: {res.get('message', '')}")

        # ---------------------------------------------------------------------
        # Torrent Commands
        # ---------------------------------------------------------------------

        elif args.command == "list":
            torrents = client.list_torrents(server_id=args.server_id)
            if not torrents:
                print("No torrents found.")
            else:
                print(f"{'HASH':<20} {'STATE':<10} {'PROGRESS':<10} {'SIZE':<12} {'NAME'}")
                print("-" * 90)
                for t in torrents:
                    hash_short = t.get('info_hash', '')[:20]
                    state = t.get('state', 'N/A')[:10]
                    progress = f"{t.get('progress', 0):.1f}%"
                    size = format_bytes(t.get('size', 0))
                    name = t.get('name', 'Unknown')[:40]
                    print(f"{hash_short:<20} {state:<10} {progress:<10} {size:<12} {name}")

        elif args.command == "add":
            if os.path.exists(args.uri):
                res = client.upload_torrent(args.uri, args.server_id,
                                           start=not args.no_start)
            else:
                res = client.add_torrent(args.uri, args.server_id,
                                        start=not args.no_start)
            print(res.get("message", "Torrent added"))

        elif args.command == "info":
            res = client.get_torrent(args.info_hash, server_id=args.server_id)
            print(json.dumps(res, indent=2))

        elif args.command == "start":
            res = client.start_torrent(args.info_hash, server_id=args.server_id)
            print(res.get("message", "Torrent started"))

        elif args.command == "stop":
            res = client.stop_torrent(args.info_hash, server_id=args.server_id)
            print(res.get("message", "Torrent stopped"))

        elif args.command == "remove":
            res = client.delete_torrent(args.info_hash, server_id=args.server_id)
            print(res.get("message", "Torrent removed"))

        # ---------------------------------------------------------------------
        # File Commands
        # ---------------------------------------------------------------------

        elif args.command == "files":
            res = client.list_torrent_files(args.info_hash, server_id=args.server_id)
            print(f"Torrent: {res.get('name', 'Unknown')}")
            print(f"Hash: {res.get('info_hash', '')}")
            print(f"Server: {res.get('server_name', '')} ({res.get('server_id', '')})")
            print(f"HTTP Downloads: {'Yes' if res.get('http_enabled') else 'No'}")
            print()
            files = res.get("files", [])
            if not files:
                print("No files found.")
            else:
                print(f"{'PROGRESS':<10} {'SIZE':<12} {'PATH'}")
                print("-" * 80)
                for f in files:
                    progress = f"{f.get('progress', 0):.1f}%"
                    size = format_bytes(f.get('size', 0))
                    path = f.get('path', '')
                    print(f"{progress:<10} {size:<12} {path}")

        elif args.command == "browse":
            res = client.list_server_files(args.server_id, args.path)
            print(f"Server: {res.get('server_name', '')} ({res.get('server_id', '')})")
            print(f"Path: /{res.get('path', '')}")
            print()
            entries = res.get("entries", [])
            if not entries:
                print("No files found.")
            else:
                print(f"{'TYPE':<6} {'SIZE':<12} {'MODIFIED':<20} {'NAME'}")
                print("-" * 80)
                for e in entries:
                    etype = "DIR" if e.get("is_dir") else "FILE"
                    size = format_bytes(e.get("size")) if not e.get("is_dir") else "-"
                    modified = e.get("modified", "")[:19] if e.get("modified") else "-"
                    name = e.get("name", "")
                    print(f"{etype:<6} {size:<12} {modified:<20} {name}")

        elif args.command == "download":
            print(f"Downloading {args.file_path}...")
            output = client.download_file(args.server_id, args.file_path,
                                         output_path=args.output)
            size = os.path.getsize(output)
            print(f"Saved to: {output} ({format_bytes(size)})")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
