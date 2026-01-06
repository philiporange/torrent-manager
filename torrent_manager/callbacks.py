"""
Torrent lifecycle callback system.

Provides a base class for implementing custom callbacks that respond to torrent
lifecycle events (added, started, stopped, completed, removed, error). Callbacks
receive comprehensive torrent information including all database-stored metadata.

Callbacks are loaded from a configurable directory (CALLBACK_DIR in config) and
executed asynchronously. Each callback file should define a class that inherits
from TorrentCallback.

Example callback implementation:

    from torrent_manager.callbacks import TorrentCallback

    class MyCallback(TorrentCallback):
        async def on_completed(self, torrent_info):
            print(f"Torrent completed: {torrent_info['name']}")

Lifecycle events:
- added: Torrent was added to a server
- started: Torrent was started/resumed
- stopped: Torrent was paused/stopped
- completed: Torrent finished downloading (100% complete)
- removed: Torrent was removed from server
- error: An error occurred with the torrent
- transfer_started: File transfer to local storage began
- transfer_completed: File transfer to local storage finished
"""

import asyncio
import importlib.util
import os
import sys
import traceback
from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from .logger import logger
from .models import Torrent, Status, Action, TorrentServer, TransferJob, UserTorrentSettings


class TorrentEvent(str, Enum):
    """Torrent lifecycle events."""
    ADDED = "added"
    STARTED = "started"
    STOPPED = "stopped"
    COMPLETED = "completed"
    REMOVED = "removed"
    ERROR = "error"
    TRANSFER_STARTED = "transfer_started"
    TRANSFER_COMPLETED = "transfer_completed"


@dataclass
class TorrentInfo:
    """
    Complete torrent information passed to callbacks.

    Contains current state from the torrent client plus all related
    database records for the torrent.
    """
    # Core identification
    info_hash: str
    name: str
    server_id: str
    server_name: str
    server_type: str

    # Current state from client
    size: int = 0
    progress: float = 0.0
    state: str = ""
    is_active: bool = False
    is_complete: bool = False
    is_private: bool = False
    download_rate: int = 0
    upload_rate: int = 0
    seeders: int = 0
    leechers: int = 0
    ratio: float = 0.0
    base_path: str = ""
    labels: List[str] = field(default_factory=list)

    # Database records
    db_torrent: Optional[Dict[str, Any]] = None
    db_statuses: List[Dict[str, Any]] = field(default_factory=list)
    db_actions: List[Dict[str, Any]] = field(default_factory=list)
    db_server: Optional[Dict[str, Any]] = None
    db_transfers: List[Dict[str, Any]] = field(default_factory=list)
    db_settings: Optional[Dict[str, Any]] = None

    # Event metadata
    event: Optional[TorrentEvent] = None
    event_time: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "info_hash": self.info_hash,
            "name": self.name,
            "server_id": self.server_id,
            "server_name": self.server_name,
            "server_type": self.server_type,
            "size": self.size,
            "progress": self.progress,
            "state": self.state,
            "is_active": self.is_active,
            "is_complete": self.is_complete,
            "is_private": self.is_private,
            "download_rate": self.download_rate,
            "upload_rate": self.upload_rate,
            "seeders": self.seeders,
            "leechers": self.leechers,
            "ratio": self.ratio,
            "base_path": self.base_path,
            "labels": self.labels,
            "db_torrent": self.db_torrent,
            "db_statuses": self.db_statuses,
            "db_actions": self.db_actions,
            "db_server": self.db_server,
            "db_transfers": self.db_transfers,
            "db_settings": self.db_settings,
            "event": self.event.value if self.event else None,
            "event_time": self.event_time.isoformat(),
            "error_message": self.error_message,
        }


class TorrentCallback(ABC):
    """
    Base class for torrent lifecycle callbacks.

    Subclass this to implement custom behavior for torrent events.
    All methods receive a TorrentInfo object with complete torrent data.

    Methods are called asynchronously. Each callback runs in its own
    context so one slow callback doesn't block others.
    """

    async def on_added(self, torrent_info: TorrentInfo) -> None:
        """Called when a torrent is added to a server."""
        pass

    async def on_started(self, torrent_info: TorrentInfo) -> None:
        """Called when a torrent is started/resumed."""
        pass

    async def on_stopped(self, torrent_info: TorrentInfo) -> None:
        """Called when a torrent is paused/stopped."""
        pass

    async def on_completed(self, torrent_info: TorrentInfo) -> None:
        """Called when a torrent finishes downloading (reaches 100%)."""
        pass

    async def on_removed(self, torrent_info: TorrentInfo) -> None:
        """Called when a torrent is removed from a server."""
        pass

    async def on_error(self, torrent_info: TorrentInfo) -> None:
        """Called when an error occurs with a torrent."""
        pass

    async def on_transfer_started(self, torrent_info: TorrentInfo) -> None:
        """Called when file transfer to local storage begins."""
        pass

    async def on_transfer_completed(self, torrent_info: TorrentInfo) -> None:
        """Called when file transfer to local storage finishes."""
        pass


def get_torrent_db_info(info_hash: str, server_id: str) -> Dict[str, Any]:
    """
    Retrieve all database records related to a torrent.

    Returns a dict with:
    - torrent: The Torrent record (or None)
    - statuses: List of recent Status records
    - actions: List of recent Action records
    - server: The TorrentServer record (or None)
    - transfers: List of TransferJob records
    - settings: UserTorrentSettings record (or None)

    Database errors are caught and logged, returning empty results.
    """
    result = {
        "torrent": None,
        "statuses": [],
        "actions": [],
        "server": None,
        "transfers": [],
        "settings": None,
    }

    info_hash_upper = info_hash.upper()

    try:
        # Get torrent record
        torrent = Torrent.get_or_none(
            (Torrent.torrent_hash == info_hash_upper) &
            (Torrent.server_id == server_id)
        )
        if torrent:
            result["torrent"] = {
                "torrent_hash": torrent.torrent_hash,
                "server_id": torrent.server_id,
                "name": torrent.name,
                "path": torrent.path,
                "files": torrent.files,
                "size": torrent.size,
                "is_private": torrent.is_private,
                "timestamp": torrent.timestamp.isoformat() if torrent.timestamp else None,
            }
    except Exception as e:
        logger.debug(f"Could not fetch torrent record: {e}")

    try:
        # Get recent status records (last 10)
        statuses = Status.select().where(
            (Status.torrent_hash == info_hash_upper) &
            (Status.server_id == server_id)
        ).order_by(Status.timestamp.desc()).limit(10)
        result["statuses"] = [
            {
                "status": s.status,
                "progress": s.progress,
                "seeders": s.seeders,
                "leechers": s.leechers,
                "down_rate": s.down_rate,
                "up_rate": s.up_rate,
                "is_private": s.is_private,
                "timestamp": s.timestamp.isoformat() if s.timestamp else None,
            }
            for s in statuses
        ]
    except Exception as e:
        logger.debug(f"Could not fetch status records: {e}")

    try:
        # Get recent action records (last 20)
        actions = Action.select().where(
            (Action.torrent_hash == info_hash_upper) &
            (Action.server_id == server_id)
        ).order_by(Action.timestamp.desc()).limit(20)
        result["actions"] = [
            {
                "action": a.action,
                "timestamp": a.timestamp.isoformat() if a.timestamp else None,
            }
            for a in actions
        ]
    except Exception as e:
        logger.debug(f"Could not fetch action records: {e}")

    server = None
    try:
        # Get server record
        server = TorrentServer.get_or_none(TorrentServer.id == server_id)
        if server:
            result["server"] = {
                "id": server.id,
                "user_id": server.user_id,
                "name": server.name,
                "server_type": server.server_type,
                "host": server.host,
                "port": server.port,
                "enabled": server.enabled,
                "is_default": server.is_default,
                "auto_download_enabled": server.auto_download_enabled,
                "auto_download_path": server.auto_download_path,
                "auto_delete_remote": server.auto_delete_remote,
            }
    except Exception as e:
        logger.debug(f"Could not fetch server record: {e}")

    try:
        # Get transfer jobs
        transfers = TransferJob.select().where(
            (TransferJob.torrent_hash == info_hash_upper) &
            (TransferJob.server_id == server_id)
        ).order_by(TransferJob.created_at.desc()).limit(10)
        result["transfers"] = [
            {
                "id": t.id,
                "status": t.status,
                "progress_percent": t.progress_percent,
                "remote_path": t.remote_path,
                "local_path": t.local_path,
                "error": t.error,
                "triggered_by": t.triggered_by,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in transfers
        ]
    except Exception as e:
        logger.debug(f"Could not fetch transfer records: {e}")

    try:
        # Get user settings (if server has user_id)
        if server:
            settings = UserTorrentSettings.get_or_none(
                (UserTorrentSettings.user_id == server.user_id) &
                (UserTorrentSettings.server_id == server_id) &
                (UserTorrentSettings.torrent_hash == info_hash_upper)
            )
            if settings:
                result["settings"] = {
                    "download_path": settings.download_path,
                    "auto_download": settings.auto_download,
                    "auto_delete_remote": settings.auto_delete_remote,
                }
    except Exception as e:
        logger.debug(f"Could not fetch user settings: {e}")

    return result


def build_torrent_info(
    torrent_data: Dict[str, Any],
    event: TorrentEvent,
    error_message: Optional[str] = None
) -> TorrentInfo:
    """
    Build a TorrentInfo object from client torrent data.

    Args:
        torrent_data: Dict from torrent client (list_torrents output)
        event: The lifecycle event being triggered
        error_message: Optional error message for error events

    Returns:
        TorrentInfo with all available data
    """
    info_hash = torrent_data.get("info_hash", "").upper()
    server_id = torrent_data.get("server_id", "")

    # Get database info
    db_info = get_torrent_db_info(info_hash, server_id)

    return TorrentInfo(
        info_hash=info_hash,
        name=torrent_data.get("name", ""),
        server_id=server_id,
        server_name=torrent_data.get("server_name", ""),
        server_type=torrent_data.get("server_type", ""),
        size=torrent_data.get("size", 0),
        progress=torrent_data.get("progress", 0.0),
        state=torrent_data.get("state", ""),
        is_active=torrent_data.get("is_active", False),
        is_complete=torrent_data.get("complete", False),
        is_private=torrent_data.get("is_private", False),
        download_rate=torrent_data.get("down_rate", 0),
        upload_rate=torrent_data.get("up_rate", 0),
        seeders=torrent_data.get("seeders", 0),
        leechers=torrent_data.get("leechers", 0),
        ratio=torrent_data.get("ratio", 0.0),
        base_path=torrent_data.get("base_path", ""),
        labels=torrent_data.get("labels", []),
        db_torrent=db_info["torrent"],
        db_statuses=db_info["statuses"],
        db_actions=db_info["actions"],
        db_server=db_info["server"],
        db_transfers=db_info["transfers"],
        db_settings=db_info["settings"],
        event=event,
        event_time=datetime.now(),
        error_message=error_message,
    )


class CallbackManager:
    """
    Manages loading and dispatching of torrent callbacks.

    Loads callback classes from Python files in the configured callback
    directory. Each file can define one or more TorrentCallback subclasses.
    """

    def __init__(self, callback_dir: Optional[str] = None):
        """
        Initialize the callback manager.

        Args:
            callback_dir: Directory containing callback scripts.
                         If None, uses Config.CALLBACK_DIR.
        """
        self._callbacks: List[TorrentCallback] = []
        self._callback_dir = callback_dir
        self._loaded = False

    def _get_callback_dir(self) -> Optional[str]:
        """Get the callback directory from config or init."""
        if self._callback_dir:
            return self._callback_dir
        from .config import Config
        return getattr(Config, "CALLBACK_DIR", None)

    def load_callbacks(self) -> None:
        """
        Load all callback classes from the callback directory.

        Scans the directory for .py files, imports them, and instantiates
        any TorrentCallback subclasses found.
        """
        self._callbacks = []
        callback_dir = self._get_callback_dir()

        if not callback_dir:
            logger.debug("No callback directory configured")
            self._loaded = True
            return

        callback_path = Path(callback_dir)
        if not callback_path.exists():
            logger.debug(f"Callback directory does not exist: {callback_dir}")
            self._loaded = True
            return

        if not callback_path.is_dir():
            logger.warning(f"Callback path is not a directory: {callback_dir}")
            self._loaded = True
            return

        # Find all Python files
        py_files = list(callback_path.glob("*.py"))
        if not py_files:
            logger.debug(f"No callback scripts found in {callback_dir}")
            self._loaded = True
            return

        logger.info(f"Loading callbacks from {callback_dir}")

        for py_file in py_files:
            if py_file.name.startswith("_"):
                continue

            try:
                self._load_callback_file(py_file)
            except Exception as e:
                logger.error(f"Failed to load callback {py_file.name}: {e}")
                logger.debug(traceback.format_exc())

        logger.info(f"Loaded {len(self._callbacks)} callback(s)")
        self._loaded = True

    def _load_callback_file(self, filepath: Path) -> None:
        """Load callback classes from a single Python file."""
        module_name = f"torrent_callback_{filepath.stem}"

        spec = importlib.util.spec_from_file_location(module_name, filepath)
        if spec is None or spec.loader is None:
            logger.warning(f"Could not load spec for {filepath}")
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error(f"Error executing {filepath.name}: {e}")
            del sys.modules[module_name]
            raise

        # Find TorrentCallback subclasses
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, TorrentCallback)
                and obj is not TorrentCallback
            ):
                try:
                    instance = obj()
                    self._callbacks.append(instance)
                    logger.debug(f"Loaded callback: {name} from {filepath.name}")
                except Exception as e:
                    logger.error(f"Failed to instantiate {name}: {e}")

    def register(self, callback: TorrentCallback) -> None:
        """
        Register a callback instance directly.

        Args:
            callback: TorrentCallback instance to register
        """
        if not isinstance(callback, TorrentCallback):
            raise TypeError("callback must be a TorrentCallback instance")
        self._callbacks.append(callback)
        logger.debug(f"Registered callback: {callback.__class__.__name__}")

    def unregister(self, callback: TorrentCallback) -> None:
        """
        Unregister a callback instance.

        Args:
            callback: TorrentCallback instance to unregister
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)
            logger.debug(f"Unregistered callback: {callback.__class__.__name__}")

    async def dispatch(
        self,
        event: TorrentEvent,
        torrent_data: Dict[str, Any],
        error_message: Optional[str] = None
    ) -> None:
        """
        Dispatch an event to all registered callbacks.

        Args:
            event: The lifecycle event
            torrent_data: Dict from torrent client
            error_message: Optional error message for error events
        """
        if not self._loaded:
            self.load_callbacks()

        if not self._callbacks:
            return

        torrent_info = build_torrent_info(torrent_data, event, error_message)

        # Map events to methods
        method_map = {
            TorrentEvent.ADDED: "on_added",
            TorrentEvent.STARTED: "on_started",
            TorrentEvent.STOPPED: "on_stopped",
            TorrentEvent.COMPLETED: "on_completed",
            TorrentEvent.REMOVED: "on_removed",
            TorrentEvent.ERROR: "on_error",
            TorrentEvent.TRANSFER_STARTED: "on_transfer_started",
            TorrentEvent.TRANSFER_COMPLETED: "on_transfer_completed",
        }

        method_name = method_map.get(event)
        if not method_name:
            logger.warning(f"Unknown event type: {event}")
            return

        # Dispatch to all callbacks concurrently
        tasks = []
        for callback in self._callbacks:
            method = getattr(callback, method_name, None)
            if method:
                tasks.append(self._safe_call(callback, method, torrent_info))

        if tasks:
            await asyncio.gather(*tasks)

    async def _safe_call(
        self,
        callback: TorrentCallback,
        method,
        torrent_info: TorrentInfo
    ) -> None:
        """Call a callback method with error handling."""
        try:
            await method(torrent_info)
        except Exception as e:
            logger.error(
                f"Callback {callback.__class__.__name__}.{method.__name__} "
                f"failed for {torrent_info.name}: {e}"
            )
            logger.debug(traceback.format_exc())


# Global callback manager instance
_callback_manager: Optional[CallbackManager] = None


def get_callback_manager() -> CallbackManager:
    """Get the global callback manager instance."""
    global _callback_manager
    if _callback_manager is None:
        _callback_manager = CallbackManager()
    return _callback_manager


async def dispatch_event(
    event: TorrentEvent,
    torrent_data: Dict[str, Any],
    error_message: Optional[str] = None
) -> None:
    """
    Dispatch a torrent lifecycle event to all callbacks.

    Convenience function that uses the global callback manager.

    Args:
        event: The lifecycle event
        torrent_data: Dict from torrent client containing at minimum
                     info_hash, server_id, server_name, server_type
        error_message: Optional error message for error events
    """
    manager = get_callback_manager()
    await manager.dispatch(event, torrent_data, error_message)
