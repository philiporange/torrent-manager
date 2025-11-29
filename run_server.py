#!/usr/bin/env python3

import subprocess
import sys
import os

def main():
    print("Starting Torrent Manager API server...")
    # Construct the command to run the server as a module
    command = [sys.executable, "-m", "torrent_manager.server"]

    # Pass along any arguments from start_server.py to the actual server
    if len(sys.argv) > 1:
        command.extend(sys.argv[1:])

    try:
        # Execute the command, passing along stdout/stderr
        subprocess.run(command, check=True)
    except FileNotFoundError:
        print(f"Error: Python interpreter not found at {sys.executable}", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error: Server process exited with code {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
