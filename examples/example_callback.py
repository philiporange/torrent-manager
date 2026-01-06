"""
Example torrent lifecycle callback.

This example demonstrates how to create a callback that responds to torrent
lifecycle events. To use callbacks:

1. Set CALLBACK_DIR in your environment or .env file to point to a directory
   containing your callback scripts:

   export CALLBACK_DIR="/path/to/callbacks"

2. Create Python files in that directory, each defining one or more classes
   that inherit from TorrentCallback.

3. The CallbackManager will automatically load and instantiate all callback
   classes when the server starts.

Example usage:
    # Copy this file to your callback directory
    cp examples/example_callback.py /path/to/callbacks/

    # Set the environment variable
    export CALLBACK_DIR="/path/to/callbacks"

    # Start the server - callbacks will be loaded automatically
    python run.py
"""

from torrent_manager.callbacks import TorrentCallback, TorrentInfo


class LoggingCallback(TorrentCallback):
    """
    Example callback that logs all torrent lifecycle events.

    This demonstrates the basic structure of a callback and what
    information is available in the TorrentInfo object.
    """

    async def on_added(self, torrent_info: TorrentInfo) -> None:
        """Called when a torrent is added to a server."""
        print(f"[ADDED] {torrent_info.name}")
        print(f"  Hash: {torrent_info.info_hash}")
        print(f"  Server: {torrent_info.server_name} ({torrent_info.server_type})")
        print(f"  Size: {torrent_info.size / 1024 / 1024:.2f} MB")

    async def on_started(self, torrent_info: TorrentInfo) -> None:
        """Called when a torrent is started/resumed."""
        print(f"[STARTED] {torrent_info.name}")
        print(f"  Progress: {torrent_info.progress:.1f}%")

    async def on_stopped(self, torrent_info: TorrentInfo) -> None:
        """Called when a torrent is paused/stopped."""
        print(f"[STOPPED] {torrent_info.name}")
        print(f"  Progress: {torrent_info.progress:.1f}%")

    async def on_completed(self, torrent_info: TorrentInfo) -> None:
        """Called when a torrent finishes downloading (reaches 100%)."""
        print(f"[COMPLETED] {torrent_info.name}")
        print(f"  Size: {torrent_info.size / 1024 / 1024:.2f} MB")
        print(f"  Path: {torrent_info.base_path}")
        print(f"  Private: {torrent_info.is_private}")

        # Access database records
        if torrent_info.db_server:
            print(f"  Server auto-download: {torrent_info.db_server.get('auto_download_enabled')}")

    async def on_removed(self, torrent_info: TorrentInfo) -> None:
        """Called when a torrent is removed from a server."""
        print(f"[REMOVED] {torrent_info.name}")
        print(f"  Final progress: {torrent_info.progress:.1f}%")

    async def on_error(self, torrent_info: TorrentInfo) -> None:
        """Called when an error occurs with a torrent."""
        print(f"[ERROR] {torrent_info.name}")
        print(f"  Error: {torrent_info.error_message}")

    async def on_transfer_started(self, torrent_info: TorrentInfo) -> None:
        """Called when file transfer to local storage begins."""
        print(f"[TRANSFER STARTED] {torrent_info.name}")
        print(f"  Size: {torrent_info.size / 1024 / 1024:.2f} MB")

    async def on_transfer_completed(self, torrent_info: TorrentInfo) -> None:
        """Called when file transfer to local storage finishes."""
        print(f"[TRANSFER COMPLETED] {torrent_info.name}")


class NotificationCallback(TorrentCallback):
    """
    Example callback that could send notifications.

    This demonstrates a more practical callback that you might use
    to integrate with external systems like Discord, Slack, email, etc.
    """

    async def on_completed(self, torrent_info: TorrentInfo) -> None:
        """Send notification when download completes."""
        # Example: Send to a webhook
        # import httpx
        # async with httpx.AsyncClient() as client:
        #     await client.post("https://hooks.example.com/webhook", json={
        #         "event": "torrent_completed",
        #         "name": torrent_info.name,
        #         "size": torrent_info.size,
        #         "hash": torrent_info.info_hash,
        #     })
        pass

    async def on_transfer_completed(self, torrent_info: TorrentInfo) -> None:
        """Send notification when transfer to local storage completes."""
        # Example: Run a local script
        # import asyncio
        # await asyncio.create_subprocess_exec(
        #     "/path/to/notify.sh",
        #     torrent_info.name,
        #     torrent_info.base_path
        # )
        pass


class MediaProcessingCallback(TorrentCallback):
    """
    Example callback for media processing workflows.

    This demonstrates how you might trigger post-processing
    when media files finish downloading.
    """

    # File extensions to process
    MEDIA_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov', '.m4v'}

    async def on_transfer_completed(self, torrent_info: TorrentInfo) -> None:
        """Trigger media processing after transfer completes."""
        # Check if this looks like media content
        name_lower = torrent_info.name.lower()
        is_media = any(name_lower.endswith(ext) for ext in self.MEDIA_EXTENSIONS)

        if is_media:
            print(f"[MEDIA] Would process: {torrent_info.name}")
            # Example: Trigger Plex scan, rename files, etc.
            # import asyncio
            # await asyncio.create_subprocess_exec(
            #     "python", "/path/to/media_processor.py",
            #     "--path", torrent_info.base_path,
            #     "--hash", torrent_info.info_hash
            # )
