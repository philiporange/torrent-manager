#!/usr/bin/env python3

import subprocess
import sys
import os

def main():
    # Construct the command to run the cli as a module
    command = [sys.executable, "-m", "torrent_manager.cli"]

    # Pass along any arguments
    if len(sys.argv) > 1:
        command.extend(sys.argv[1:])

    try:
        # Execute the command
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
