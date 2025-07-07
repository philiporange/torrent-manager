import time
import os
import shutil

from .config import Config
from .logger import logger


COMPLETE_PATH = Config.COMPLETE_PATH


def move(client, info_hash, destination=COMPLETE_PATH):
    logger.info(f"Moving {info_hash} to {destination}")
    name = client.d.name(info_hash)
    is_multi_file = client.d.is_multi_file(info_hash) == 1
    base_path = os.path.abspath(client.d.base_path(info_hash))
    destination_path = os.path.join(destination, name)
    destination_path = os.path.abspath(destination_path)

    # Stop the torrent
    client.d.stop(info_hash)
    while client.d.is_active(info_hash) == 1:  # Wait until stopped
        time.sleep(1)

    # Move torrent
    if os.path.exists(destination_path):
        shutil.rmtree(destination_path)

    if is_multi_file:
        shutil.copytree(base_path, destination_path)
    else:
        shutil.copy2(base_path, destination_path)

    # Update torrent directory in rTorrent
    client.d.directory.set(info_hash, destination)

    # Restart the torrent
    client.d.start(info_hash)
    while client.d.is_active(info_hash) == 0:
        time.sleep(1)

    # Remove old torrent files
    if is_multi_file:
        shutil.rmtree(base_path)
    else:
        os.remove(base_path)


def move_torrent(client, info_hash, new_location):
    """
    Moves a torrent's data from its current location to a new location.
    This method handles both single-file and multi-file torrents.

    Args:
        info_hash (str): The info hash of the torrent to move.
        new_location (str): The new base directory for the torrent.

    Returns:
        bool: True if the move was successful, False otherwise.
    """
    try:
        # Stop the torrent to prevent data corruption during move
        client.stop(info_hash)

        current_path = client.actual_torrent_path(info_hash)
        is_multi_file = client.is_multi_file(info_hash)
        torrent_name = client.name(info_hash)

        if is_multi_file:
            # For multi-file torrents, move the entire directory
            new_path = os.path.join(new_location, torrent_name)
            shutil.move(current_path, new_path)
        else:
            # For single-file torrents, move the file and ensure the directory exists
            os.makedirs(new_location, exist_ok=True)
            new_path = os.path.join(new_location, os.path.basename(current_path))
            shutil.move(current_path, new_path)

        # Update the torrent's directory in rTorrent
        client.d.directory.set(info_hash, new_location)

        # If it's a single-file torrent, we need to update the base_filename as well
        if not is_multi_file:
            client.d.base_filename.set(info_hash, os.path.basename(new_path))

        # Restart the torrent
        client.start(info_hash)

        logger.info(f"Successfully moved torrent {info_hash} to {new_location}")
        return True

    except Exception as e:
        logger.error(f"Failed to move torrent {info_hash}: {str(e)}")
        # Attempt to restart the torrent in case of failure
        client.start(info_hash)
        return False
