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
            pass  # Ignore errors loading session

def clear_session():
    """Remove the saved session file."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()

def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"

def main():
    parser = argparse.ArgumentParser(description="Torrent Manager CLI")
    parser.add_argument("--url", default="http://localhost:8144", help="API URL")
    parser.add_argument("--api-key", help="API Key (optional)")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Auth
    auth_parser = subparsers.add_parser("login", help="Login to the server")
    auth_parser.add_argument("username", help="Username")
    auth_parser.add_argument("password", help="Password")
    
    subparsers.add_parser("logout", help="Logout")
    
    reg_parser = subparsers.add_parser("register", help="Register a new user")
    reg_parser.add_argument("username", help="Username")
    reg_parser.add_argument("password", help="Password")
    
    subparsers.add_parser("whoami", help="Get current user info")

    # Torrents
    subparsers.add_parser("list", help="List all torrents")
    
    add_parser = subparsers.add_parser("add", help="Add a torrent")
    add_parser.add_argument("uri", help="Magnet URI, URL, or file path")
    add_parser.add_argument("--no-start", action="store_true", help="Don't start immediately")
    
    action_parser = subparsers.add_parser("start", help="Start a torrent")
    action_parser.add_argument("info_hash", help="Torrent Info Hash")
    
    stop_parser = subparsers.add_parser("stop", help="Stop a torrent")
    stop_parser.add_argument("info_hash", help="Torrent Info Hash")
    
    rm_parser = subparsers.add_parser("remove", help="Remove a torrent")
    rm_parser.add_argument("info_hash", help="Torrent Info Hash")
    
    # API Keys
    key_parser = subparsers.add_parser("create-key", help="Create an API key")
    key_parser.add_argument("name", help="Key name")
    key_parser.add_argument("--days", type=int, help="Expiration in days")
    
    subparsers.add_parser("list-keys", help="List API keys")
    
    revoke_parser = subparsers.add_parser("revoke-key", help="Revoke an API key")
    revoke_parser.add_argument("prefix", help="Key prefix")

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return

    client = TorrentManagerClient(base_url=args.url, api_key=args.api_key)
    
    # Load session unless we are providing an API key
    if not args.api_key:
        load_session(client)

    try:
        if args.command == "login":
            res = client.login(args.username, args.password, remember_me=True)
            save_session(client)
            print(f"Logged in as {res['username']}")
            
        elif args.command == "logout":
            client.logout()
            clear_session()
            print("Logged out")
            
        elif args.command == "register":
            res = client.register(args.username, args.password)
            print(f"Registered user {res['username']}")
            
        elif args.command == "whoami":
            res = client.get_me()
            print(json.dumps(res, indent=2))
            
        elif args.command == "list":
            torrents = client.list_torrents()
            if not torrents:
                print("No torrents found.")
            else:
                print(f"{'HASH':<40} {'STATE':<10} {'SIZE':<12} {'DL SPEED':<12} {'NAME'}")
                print("-" * 100)
                for t in torrents:
                    size = format_bytes(t.get('size', 0))
                    speed = format_bytes(t.get('download_rate', 0)) + "/s"
                    print(f"{t['info_hash']:<40} {t.get('state', 'N/A'):<10} {size:<12} {speed:<12} {t.get('name', 'Unknown')}")

        elif args.command == "add":
            if os.path.exists(args.uri):
                res = client.upload_torrent(args.uri, start=not args.no_start)
            elif args.uri.startswith("magnet:"):
                res = client.add_magnet(args.uri, start=not args.no_start)
            else:
                res = client.add_url(args.uri, start=not args.no_start)
            print(res['message'])

        elif args.command == "start":
            res = client.start_torrent(args.info_hash)
            print(res['message'])
            
        elif args.command == "stop":
            res = client.stop_torrent(args.info_hash)
            print(res['message'])
            
        elif args.command == "remove":
            res = client.delete_torrent(args.info_hash)
            print(res['message'])
            
        elif args.command == "create-key":
            res = client.create_api_key(args.name, args.days)
            print(f"Created API Key: {res['api_key']}")
            print("SAVE THIS KEY! It will not be shown again.")
            
        elif args.command == "list-keys":
            keys = client.list_api_keys()
            print(json.dumps(keys, indent=2))
            
        elif args.command == "revoke-key":
            res = client.revoke_api_key(args.prefix)
            print(res['message'])
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
