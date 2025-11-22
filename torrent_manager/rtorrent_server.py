"""
rTorrent Server Manager

Quick launcher for the rTorrent Docker container. Provides commands to start, stop,
check status, and test connectivity to the rTorrent server.
"""

import argparse
import json
import sys
import time

from .docker_rtorrent import DockerRTorrent
from .rtorrent_client import RTorrentClient
from .magnet_link import MagnetLink


def start_server(args):
    """Start the rTorrent Docker container."""
    docker = DockerRTorrent()
    print("Starting rTorrent Docker container...")
    docker.start()

    container_ip = docker.get_container_ip()
    print(f"\n✓ rTorrent server started successfully")
    print(f"  Container IP: {container_ip}")
    print(f"\nTo test connectivity: python rtorrent_server.py test")
    print(f"To stop server: python rtorrent_server.py stop")


def stop_server(args):
    """Stop the rTorrent Docker container."""
    docker = DockerRTorrent()
    print("Stopping rTorrent Docker container...")
    docker.stop()
    print("✓ rTorrent server stopped")


def status_server(args):
    """Check the status of the rTorrent Docker container."""
    docker = DockerRTorrent()
    try:
        container_ip = docker.get_container_ip()
        print(f"✓ rTorrent server is running")
        print(f"  Container IP: {container_ip}")

        try:
            client = RTorrentClient()
            version = client.system.client_version()
            print(f"  Version: {version}")

            torrents = list(client.list_torrents())
            print(f"  Active torrents: {len(torrents)}")
        except Exception as e:
            print(f"  Warning: Could not connect to rTorrent client: {e}")
    except Exception as e:
        print(f"✗ rTorrent server is not running")


def test_connection(args):
    """Test connection to the rTorrent server."""
    try:
        client = RTorrentClient()
        version = client.system.client_version()
        print(f"✓ Connected to rTorrent: {version}")

        torrents = list(client.list_torrents(files=args.files))
        print(f"  Total torrents: {len(torrents)}")

        if args.verbose and torrents:
            print("\nTorrent details:")
            for torrent in torrents:
                print(json.dumps(torrent, indent=2))

        return True
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        print("\nTroubleshooting:")
        print("  1. Check if server is running: python rtorrent_server.py status")
        print("  2. Start the server: python rtorrent_server.py start")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="rTorrent Server Manager - Quick launcher for Docker rTorrent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python rtorrent_server.py start          Start the rTorrent server
  python rtorrent_server.py stop           Stop the rTorrent server
  python rtorrent_server.py status         Check server status
  python rtorrent_server.py test           Test connection
  python rtorrent_server.py test -v        Test with verbose output
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start the rTorrent Docker container")
    start_parser.set_defaults(func=start_server)

    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop the rTorrent Docker container")
    stop_parser.set_defaults(func=stop_server)

    # Status command
    status_parser = subparsers.add_parser("status", help="Check server status")
    status_parser.set_defaults(func=status_server)

    # Test command
    test_parser = subparsers.add_parser("test", help="Test connection to rTorrent")
    test_parser.add_argument("-v", "--verbose", action="store_true", help="Show detailed torrent information")
    test_parser.add_argument("-f", "--files", action="store_true", help="Include file information for each torrent")
    test_parser.set_defaults(func=test_connection)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
    