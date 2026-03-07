"""
Transfer service for downloading completed torrents via rsync over SSH.

Manages a queue of transfer jobs, executes rsync with progress parsing,
handles retries, and optionally deletes remote files after seeding completes.
The service runs as a background asyncio task alongside the TorrentPoller.

Transfer flow:
1. TorrentPoller detects completion -> calls queue_transfer()
2. TransferJob created in database with status "pending"
3. Background loop picks up pending jobs
4. rsync dry-run to check if transfer needed -> skip if already complete
5. rsync subprocess executed, progress parsed and saved to DB
6. On success: mark "completed", check for auto-delete
7. On failure: retry up to max_retries, then mark "failed"

Auto-delete flow (seeding-aware):
1. Transfer completes, job.auto_delete_after=True
2. Check if torrent is still actively seeding (complete AND active)
3. If seeding: defer deletion, job.remote_deleted remains False
4. process_pending_deletions() periodically rechecks deferred deletions
5. When seeding stops: delete torrent/files, set job.remote_deleted=True

Error handling:
- Respects poller's circuit breaker: skips deletion checks when server is unreachable
- Uses reduced timeout (10s) for deletion checks to prevent blocking
- Implements reduced-frequency logging for persistent server connection failures
- Logs first error, 5th error, then every 10 minutes to reduce log spam
- Logs seeding deferrals at most every 10 minutes to prevent log spam
- Gives up after 20 consecutive deletion failures to prevent infinite retry loops
- Immediately marks torrent as deleted if "info-hash not found" error received
"""

import asyncio
import os
import re
import secrets
import shlex
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, List

from .models import TransferJob, TorrentServer, UserTorrentSettings
from .logger import logger
from .config import Config
from .callbacks import dispatch_event, TorrentEvent


@dataclass
class TransferProgress:
    """Parsed rsync progress information."""
    bytes_transferred: int
    percent: float
    speed: str


class TransferService:
    """
    Manages file transfers from remote torrent servers to local storage.

    Uses rsync over SSH for robust, resumable transfers with compression.
    Runs transfers concurrently up to max_concurrent limit.
    """

    # Matches rsync progress output like: "1,234,567  45%  12.34MB/s"
    RSYNC_PROGRESS_PATTERN = re.compile(
        r'^\s*([\d,]+)\s+(\d+)%\s+([\d.]+\S+/s)'
    )

    # Matches "Total transferred file size: 0 bytes" from rsync --stats
    RSYNC_TRANSFER_SIZE_PATTERN = re.compile(
        r'Total transferred file size:\s*([\d,]+)\s*bytes'
    )

    def __init__(self, max_concurrent: int = 2):
        self._max_concurrent = max_concurrent
        self._running = False
        self._active_jobs: Dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        # Track deletion errors for reduced-frequency logging
        self._deletion_errors: Dict[str, Dict[str, Any]] = {}
        # Track seeding deferrals for reduced-frequency logging
        self._seeding_deferrals: Dict[str, float] = {}  # job_key -> last_logged_time

    def queue_transfer(
        self,
        server: TorrentServer,
        torrent: Dict[str, Any],
        user_id: str,
        triggered_by: str = "auto",
        download_path_override: Optional[str] = None
    ) -> Optional[TransferJob]:
        """
        Queue a new transfer job for a completed torrent.

        Returns the created TransferJob, or None if:
        - Auto-download is disabled and no override provided
        - A pending/running job already exists for this torrent
        - No download path is configured
        """
        torrent_hash = torrent["info_hash"].upper()

        # Check for existing active job
        existing = TransferJob.select().where(
            (TransferJob.torrent_hash == torrent_hash) &
            (TransferJob.server_id == server.id) &
            (TransferJob.status.in_(["pending", "running"]))
        ).first()

        if existing:
            logger.debug(f"Transfer already queued/running for {torrent_hash[:8]}")
            return None

        # Get per-torrent settings if they exist
        settings = UserTorrentSettings.get_or_none(
            (UserTorrentSettings.user_id == user_id) &
            (UserTorrentSettings.server_id == server.id) &
            (UserTorrentSettings.torrent_hash == torrent_hash)
        )

        # Check if auto-download is enabled (per-torrent overrides server)
        auto_enabled = server.auto_download_enabled
        if settings and settings.auto_download is not None:
            auto_enabled = settings.auto_download

        # For auto-triggered, respect the enabled setting; manual always proceeds
        if triggered_by == "auto" and not auto_enabled:
            return None

        # Determine local download path (override > per-torrent > server)
        local_base = download_path_override
        if not local_base and settings and settings.download_path:
            local_base = settings.download_path
        if not local_base:
            local_base = server.auto_download_path

        if not local_base:
            logger.warning(f"No download path configured for server {server.name}")
            return None

        # Determine auto-delete setting
        auto_delete = server.auto_delete_remote
        if settings and settings.auto_delete_remote is not None:
            auto_delete = settings.auto_delete_remote

        # Build paths - transfer the entire <info_hash>/ directory
        # Remote structure: <download_dir>/<info_hash>/data/<torrent_files>
        # We transfer: <download_dir>/<info_hash>/ -> <local_base>/<info_hash>/
        directory = torrent.get("directory", "")
        if directory:
            # directory is like /downloads/<info_hash>/data, go up one level
            remote_path = os.path.dirname(directory)
        elif server.download_dir:
            # Fallback: construct from download_dir and info_hash
            remote_path = os.path.join(server.download_dir, torrent_hash.lower())
        else:
            logger.warning(f"Cannot determine remote path for {torrent_hash[:8]}")
            return None

        torrent_name = torrent.get("name", torrent_hash)
        # Local path uses info_hash as directory name
        local_path = os.path.join(local_base, torrent_hash.lower())

        # Create job record
        job = TransferJob.create(
            id=secrets.token_urlsafe(16),
            user_id=user_id,
            server_id=server.id,
            torrent_hash=torrent_hash,
            torrent_name=torrent_name,
            remote_path=remote_path,
            local_path=local_path,
            total_bytes=torrent.get("size", 0),
            auto_delete_after=auto_delete,
            triggered_by=triggered_by,
            max_retries=getattr(Config, 'TRANSFER_MAX_RETRIES', 3)
        )

        logger.info(f"Queued transfer job {job.id[:8]} for {torrent_name}")
        return job

    def _build_rsync_command(self, job: TransferJob, server: TorrentServer) -> List[str]:
        """Build the rsync command with appropriate options."""
        ssh_host = server.ssh_host or server.host
        ssh_user = server.ssh_user or "root"
        ssh_port = server.ssh_port or 22

        # Build SSH command with options
        ssh_cmd = f"ssh -p {ssh_port}"
        if server.ssh_key_path:
            ssh_cmd += f" -i {shlex.quote(server.ssh_key_path)}"
        ssh_cmd += " -o StrictHostKeyChecking=accept-new -o BatchMode=yes"

        # rsync options:
        # -a: archive mode (preserves permissions, times, etc.)
        # -v: verbose
        # -z: compress during transfer
        # --progress: show progress for each file
        # --partial: keep partially transferred files
        # --partial-dir: store partial files in hidden dir
        # No trailing slash - rsync the file/dir directly to destination
        # Don't use shlex.quote - subprocess handles args correctly, quotes become literal
        remote_src = f"{ssh_user}@{ssh_host}:{job.remote_path}"

        # Destination is the parent directory - rsync will create the file/dir inside it
        local_dest = os.path.dirname(job.local_path)

        cmd = [
            "rsync",
            "-avz",
            "--progress",
            "--partial",
            "--partial-dir=.rsync-partial",
            "--protect-args",  # Prevent remote shell from interpreting special chars like []
            "-e", ssh_cmd,
            remote_src,
            local_dest + "/"  # Trailing slash on dest ensures it's treated as directory
        ]

        return cmd

    async def _check_transfer_needed(
        self, job: TransferJob, server: TorrentServer
    ) -> tuple[bool, Optional[str]]:
        """
        Check if transfer is needed using rsync --dry-run.

        Returns (needs_transfer, error_message).
        If needs_transfer is False and error_message is None, destination is complete.
        If needs_transfer is False and error_message is set, there was an error.
        """
        # Build command with --dry-run --stats instead of --progress
        ssh_host = server.ssh_host or server.host
        ssh_user = server.ssh_user or "root"
        ssh_port = server.ssh_port or 22

        ssh_cmd = f"ssh -p {ssh_port}"
        if server.ssh_key_path:
            ssh_cmd += f" -i {shlex.quote(server.ssh_key_path)}"
        ssh_cmd += " -o StrictHostKeyChecking=accept-new -o BatchMode=yes"

        remote_src = f"{ssh_user}@{ssh_host}:{job.remote_path}"
        local_dest = os.path.dirname(job.local_path)

        cmd = [
            "rsync",
            "-avz",
            "--dry-run",
            "--stats",
            "--protect-args",
            "-e", ssh_cmd,
            remote_src,
            local_dest + "/"
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            stdout, _ = await process.communicate()
            output = stdout.decode(errors='replace')

            if process.returncode != 0:
                # Dry-run failed - proceed with actual transfer to get real error
                return (True, None)

            # Parse "Total transferred file size: X bytes"
            match = self.RSYNC_TRANSFER_SIZE_PATTERN.search(output)
            if match:
                transfer_bytes = int(match.group(1).replace(",", ""))
                if transfer_bytes == 0:
                    return (False, None)  # Nothing to transfer

            # Has bytes to transfer or couldn't parse - proceed with transfer
            return (True, None)

        except Exception as e:
            logger.debug(f"Dry-run check failed: {e}")
            # On error, proceed with actual transfer
            return (True, None)

    def _parse_progress(self, line: str) -> Optional[TransferProgress]:
        """Parse rsync progress output."""
        match = self.RSYNC_PROGRESS_PATTERN.search(line)
        if match:
            bytes_str = match.group(1).replace(",", "")
            percent = float(match.group(2))
            speed = match.group(3)
            return TransferProgress(
                bytes_transferred=int(bytes_str),
                percent=percent,
                speed=speed
            )
        return None

    async def _run_transfer(self, job: TransferJob) -> bool:
        """
        Execute a single transfer job using rsync.

        Returns True on success, False on failure.
        Updates job status and progress in database.
        """
        server = TorrentServer.get_or_none(TorrentServer.id == job.server_id)
        if not server:
            job.status = "failed"
            job.error = "Server not found"
            job.save()
            return False

        # Ensure local parent directory exists before dry-run check
        os.makedirs(os.path.dirname(job.local_path), exist_ok=True)

        # Check if transfer is needed using rsync dry-run
        needs_transfer, error = await self._check_transfer_needed(job, server)
        if not needs_transfer and error is None:
            logger.info(
                f"Skipping transfer {job.id[:8]}: destination already complete"
            )
            job.status = "completed"
            job.completed_at = datetime.now()
            job.progress_percent = 100.0
            job.error = "Already exists at destination"
            job.save()
            return True

        cmd = self._build_rsync_command(job, server)
        logger.info(f"Starting transfer {job.id[:8]}: {job.torrent_name}")
        logger.debug(f"rsync command: {' '.join(cmd)}")

        # Update job status
        job.status = "running"
        job.started_at = datetime.now()
        job.save()

        # Dispatch transfer started callback
        torrent_data = {
            "info_hash": job.torrent_hash,
            "name": job.torrent_name,
            "server_id": job.server_id,
            "server_name": server.name,
            "server_type": server.server_type,
            "size": job.total_bytes,
        }
        await dispatch_event(TorrentEvent.TRANSFER_STARTED, torrent_data)

        try:
            async with self._semaphore:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT
                )

                # Read output and parse progress
                # rsync uses \r for progress updates, not \n, so read in chunks
                last_progress_save = 0
                buffer = ""
                while True:
                    chunk = await process.stdout.read(1024)
                    if not chunk:
                        break

                    buffer += chunk.decode(errors='replace')
                    # Split on both \r and \n
                    while '\r' in buffer or '\n' in buffer:
                        # Find the earliest delimiter
                        r_pos = buffer.find('\r')
                        n_pos = buffer.find('\n')
                        if r_pos == -1:
                            pos = n_pos
                        elif n_pos == -1:
                            pos = r_pos
                        else:
                            pos = min(r_pos, n_pos)

                        line_str = buffer[:pos].strip()
                        buffer = buffer[pos + 1:]

                        if line_str:
                            progress = self._parse_progress(line_str)
                            if progress:
                                job.progress_bytes = progress.bytes_transferred
                                job.progress_percent = progress.percent
                                # Save progress at most every 2 seconds to reduce DB writes
                                now = asyncio.get_event_loop().time()
                                if now - last_progress_save >= 2:
                                    job.save()
                                    last_progress_save = now

                await process.wait()

            if process.returncode == 0:
                job.status = "completed"
                job.completed_at = datetime.now()
                job.progress_percent = 100.0
                job.save()

                logger.info(f"Transfer completed: {job.torrent_name}")

                # Dispatch transfer completed callback
                await dispatch_event(TorrentEvent.TRANSFER_COMPLETED, torrent_data)

                # Handle auto-delete
                if job.auto_delete_after:
                    await self._delete_remote(job, server)

                return True
            else:
                raise Exception(f"rsync exited with code {process.returncode}")

        except asyncio.CancelledError:
            job.status = "cancelled"
            job.save()
            logger.info(f"Transfer cancelled: {job.torrent_name}")
            raise
        except Exception as e:
            logger.error(f"Transfer failed for {job.torrent_name}: {e}")
            job.error = str(e)[:500]  # Truncate long errors
            job.retry_count += 1

            if job.retry_count < job.max_retries:
                job.status = "pending"  # Will be retried
                logger.info(f"Will retry transfer ({job.retry_count}/{job.max_retries})")
            else:
                job.status = "failed"
                logger.error(f"Transfer failed after {job.max_retries} retries")

            job.save()
            return False

    async def _delete_remote(self, job: TransferJob, server: TorrentServer) -> bool:
        """
        Delete remote torrent and data after successful transfer.

        Only deletes if the torrent is not actively seeding. If still seeding,
        returns False so it can be retried later via process_pending_deletions().

        Respects the poller's circuit breaker: if the server is in cooldown due to
        connection failures, skips deletion check to avoid timeout delays.

        Returns True if deletion was performed or torrent no longer exists.
        Returns False if deletion was deferred (seeding or server unreachable).

        Gives up after 20 consecutive failures and marks the torrent as deleted
        to prevent infinite retry loops.
        """
        import time

        # Track deletion failures per job instead of per server
        job_key = f"{server.id}:{job.torrent_hash}"

        # Check if server is in circuit breaker cooldown (poller has detected it's unreachable)
        from .polling import get_poller
        poller = get_poller()
        server_cache = poller._cache.get(server.id)
        if server_cache and server_cache.skip_until > time.time():
            # Server is in cooldown, skip deletion check to avoid timeout
            logger.debug(f"Skipping deletion check for {job.torrent_name} - server {server.name} in circuit breaker cooldown")
            return False

        try:
            from .client_factory import get_client
            # Use shorter timeout for deletion checks (10s instead of 30s)
            # to prevent blocking the transfer service loop
            client = get_client(server, timeout=10)

            # Check if torrent still exists and its status
            torrent = None
            for t in client.get_torrent(job.torrent_hash):
                torrent = t
                break

            if torrent is None:
                # Torrent already removed
                logger.debug(f"Torrent already removed: {job.torrent_name}")
                job.remote_deleted = True
                job.save()
                # Clear tracking on success
                if job_key in self._deletion_errors:
                    del self._deletion_errors[job_key]
                if job_key in self._seeding_deferrals:
                    del self._seeding_deferrals[job_key]
                return True

            # Check if actively seeding (complete and active)
            if torrent.get("complete") and torrent.get("is_active"):
                # Use reduced-frequency logging for seeding deferrals (log every 10 minutes)
                current_time = time.time()
                last_logged = self._seeding_deferrals.get(job_key, 0.0)
                if (current_time - last_logged) >= 600:  # 10 minutes
                    logger.debug(f"Torrent still seeding, deferring deletion: {job.torrent_name}")
                    self._seeding_deferrals[job_key] = current_time
                # Clear error tracking - this is expected behavior, not an error
                if job_key in self._deletion_errors:
                    del self._deletion_errors[job_key]
                return False

            # Safe to delete - torrent is stopped or not seeding
            # First remove from rtorrent (don't use delete_data - it only works locally)
            client.erase(job.torrent_hash, delete_data=False)
            logger.info(f"Removed torrent from rtorrent: {job.torrent_name}")

            # Delete remote files via SSH
            await self._delete_remote_files(job, server)

            job.remote_deleted = True
            job.save()
            logger.info(f"Deleted remote data: {job.torrent_name}")
            # Clear tracking on success
            if job_key in self._deletion_errors:
                del self._deletion_errors[job_key]
            if job_key in self._seeding_deferrals:
                del self._seeding_deferrals[job_key]
            return True

        except Exception as e:
            # Use reduced-frequency error logging for persistent failures
            current_time = time.time()
            error_str = str(e)

            # Check if this is a permanent error (torrent not found)
            is_permanent_error = (
                "info-hash not found" in error_str.lower() or
                "torrent not found" in error_str.lower()
            )

            if job_key not in self._deletion_errors:
                self._deletion_errors[job_key] = {
                    'count': 0,
                    'last_logged': 0.0,
                    'first_error_time': current_time
                }

            self._deletion_errors[job_key]['count'] += 1
            error_count = self._deletion_errors[job_key]['count']
            last_logged = self._deletion_errors[job_key]['last_logged']

            # For permanent errors, give up immediately
            if is_permanent_error:
                logger.warning(
                    f"Torrent not found on remote, marking as deleted: {job.torrent_name} on {server.name}"
                )
                job.remote_deleted = True
                job.save()
                if job_key in self._deletion_errors:
                    del self._deletion_errors[job_key]
                if job_key in self._seeding_deferrals:
                    del self._seeding_deferrals[job_key]
                return True

            # Give up after 20 consecutive failures (prevents infinite retry loops)
            if error_count >= 20:
                logger.warning(
                    f"Giving up on deleting remote torrent {job.torrent_name} on {server.name} "
                    f"after {error_count} failures, marking as deleted"
                )
                job.remote_deleted = True
                job.save()
                if job_key in self._deletion_errors:
                    del self._deletion_errors[job_key]
                if job_key in self._seeding_deferrals:
                    del self._seeding_deferrals[job_key]
                return True

            # Log errors with reduced frequency for persistent failures
            # First error, 5th error, then every 10 minutes
            should_log = (
                error_count == 1 or
                error_count == 5 or
                (current_time - last_logged) >= 600
            )

            if should_log:
                if error_count == 1:
                    logger.error(f"Failed to delete remote torrent {job.torrent_name} on {server.name}: {e}")
                else:
                    logger.error(
                        f"Failed to delete remote torrent {job.torrent_name} on {server.name} "
                        f"({error_count} consecutive failures): {e}"
                    )
                self._deletion_errors[job_key]['last_logged'] = current_time

            return False

    async def _delete_remote_files(self, job: TransferJob, server: TorrentServer):
        """Delete remote files via SSH after transfer completes."""
        ssh_host = server.ssh_host or server.host
        ssh_user = server.ssh_user or "root"
        ssh_port = server.ssh_port or 22

        # Build SSH command
        ssh_args = ["ssh", "-p", str(ssh_port)]
        if server.ssh_key_path:
            ssh_args.extend(["-i", server.ssh_key_path])
        ssh_args.extend([
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "BatchMode=yes",
            f"{ssh_user}@{ssh_host}",
            f"rm -rf {shlex.quote(job.remote_path)}"
        ])

        logger.debug(f"Deleting remote files: {' '.join(ssh_args)}")

        process = await asyncio.create_subprocess_exec(
            *ssh_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        await process.wait()

        if process.returncode != 0:
            logger.warning(f"Remote file deletion may have failed (exit code {process.returncode})")

    async def process_pending_deletions(self):
        """
        Process completed transfers that are waiting for seeding to finish.

        Finds jobs with auto_delete_after=True, status=completed, and
        remote_deleted=False, then attempts deletion for each.
        """
        pending_deletions = list(TransferJob.select().where(
            (TransferJob.status == "completed") &
            (TransferJob.auto_delete_after == True) &
            (TransferJob.remote_deleted == False)
        ).limit(10))

        for job in pending_deletions:
            server = TorrentServer.get_or_none(TorrentServer.id == job.server_id)
            if server:
                await self._delete_remote(job, server)

    async def process_pending_jobs(self):
        """Process all pending transfer jobs, respecting concurrency limit."""
        pending = list(TransferJob.select().where(
            TransferJob.status == "pending"
        ).order_by(TransferJob.created_at).limit(10))

        for job in pending:
            if job.id not in self._active_jobs:
                task = asyncio.create_task(self._run_transfer(job))
                self._active_jobs[job.id] = task

                # Cleanup completed tasks
                def cleanup(t, jid=job.id):
                    self._active_jobs.pop(jid, None)
                task.add_done_callback(cleanup)

    async def run(self):
        """Main transfer processing loop."""
        self._running = True
        logger.info(f"Transfer service started (max concurrent: {self._max_concurrent})")

        deletion_check_counter = 0
        while self._running:
            try:
                await self.process_pending_jobs()

                # Check pending deletions every 60 seconds (6 iterations)
                deletion_check_counter += 1
                if deletion_check_counter >= 6:
                    await self.process_pending_deletions()
                    deletion_check_counter = 0

                await asyncio.sleep(10)  # Check every 10 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in transfer service: {e}")
                await asyncio.sleep(30)

        # Cancel active transfers on shutdown
        for task in self._active_jobs.values():
            task.cancel()

        # Wait for cancellations to complete
        if self._active_jobs:
            await asyncio.gather(*self._active_jobs.values(), return_exceptions=True)

        logger.info("Transfer service stopped")

    def stop(self):
        """Signal the service to stop."""
        self._running = False

    def get_active_count(self) -> int:
        """Return number of currently running transfers."""
        return len(self._active_jobs)


# Global service instance
_transfer_service: Optional[TransferService] = None


def get_transfer_service() -> TransferService:
    """Get the global transfer service instance, creating if needed."""
    global _transfer_service
    if _transfer_service is None:
        max_concurrent = getattr(Config, 'TRANSFER_MAX_CONCURRENT', 2)
        _transfer_service = TransferService(max_concurrent=max_concurrent)
    return _transfer_service
