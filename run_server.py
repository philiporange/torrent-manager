#!/usr/bin/env python3
"""
Torrent Manager Server Runner

Simple script to run the Torrent Manager API server.

This is a convenience wrapper around torrent_manager.server.main().
Use this script from the project root to start the server.

Usage:
    python run_server.py               # Run on default port
    python run_server.py --port 8080   # Run on custom port
    python run_server.py --reload      # Run with auto-reload (development)
"""

import sys
import os

# Add the current directory to Python path so we can import torrent_manager
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from torrent_manager.server import main

if __name__ == "__main__":
    main()