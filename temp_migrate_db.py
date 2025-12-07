#!/usr/bin/env python3
"""
Database migration script to add mount_path column to TorrentServer table.

Adds a nullable mount_path column that stores the local path to an sshfs-mounted
directory for direct file access instead of proxying through HTTP.
"""

import os
import sys
import sqlite3

# Try to get the database path from the environment or config
DB_PATH = os.getenv("SQLITE_DB_PATH", "torrent_manager.db")


def migrate():
    """Add mount_path column to torrentserver table if it doesn't exist."""
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        print("Set SQLITE_DB_PATH environment variable or ensure torrent_manager.db exists")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if column already exists
    cursor.execute("PRAGMA table_info(torrentserver)")
    columns = [row[1] for row in cursor.fetchall()]

    if "mount_path" in columns:
        print("Column 'mount_path' already exists in torrentserver table")
        conn.close()
        return

    # Add the column
    print(f"Adding 'mount_path' column to torrentserver table in {DB_PATH}...")
    cursor.execute("ALTER TABLE torrentserver ADD COLUMN mount_path VARCHAR")
    conn.commit()
    conn.close()

    print("Migration complete!")


if __name__ == "__main__":
    migrate()
