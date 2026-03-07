"""
Automatic media identification and metadata retrieval service.

Integrates torrent_match for content identification and media_metadata for
enrichment. Identifies media from torrent names and file structures, retrieves
comprehensive metadata from TMDB/IMDB, and writes Jellyfin-compatible files
to the torrent's metadata/ directory.

The service runs identification asynchronously to avoid blocking torrent
operations. Results are stored in the TorrentMetadata database table and
written to <info_hash>/metadata/ on the torrent server. Handles mount
unavailability gracefully by catching OSError and falling back to safe defaults.

Usage:
    service = get_metadata_service()
    result = await service.process_torrent(torrent_info, server)
"""

import asyncio
import json
import os
import shlex
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config
from .logger import logger
from .models import TorrentMetadata, TorrentServer


@dataclass
class IdentificationResult:
    """Result of media identification from torrent_match."""
    success: bool
    media_id: Optional[str] = None
    media_type: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    imdb_id: Optional[str] = None
    tmdb_id: Optional[int] = None
    confidence: float = 0.0
    confidence_level: str = "VERY_LOW"
    raw_result: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class MetadataResult:
    """Result of metadata retrieval from media_metadata."""
    success: bool
    metadata: Dict[str, Any] = field(default_factory=dict)
    nfo_content: Optional[str] = None
    poster_url: Optional[str] = None
    fanart_url: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ProcessingResult:
    """Complete result of torrent metadata processing."""
    torrent_hash: str
    server_id: str
    identification: Optional[IdentificationResult] = None
    metadata: Optional[MetadataResult] = None
    files_written: List[str] = field(default_factory=list)
    status: str = "pending"
    error: Optional[str] = None


class MetadataService:
    """
    Service for automatic media identification and metadata retrieval.

    Coordinates torrent_match for identification and media_metadata for
    enrichment. Handles both local mount and SSH-based file writing.
    """

    def __init__(self):
        self._matcher = None
        self._media_metadata = None
        self._jellyfin = None
        self._semaphore = asyncio.Semaphore(3)  # Max concurrent identifications
        self._task_queue: Dict[str, asyncio.Task] = {}

    @property
    def matcher(self):
        """Lazy-load TorrentMatcher."""
        if self._matcher is None:
            try:
                from torrent_match import TorrentMatcher
                self._matcher = TorrentMatcher(
                    enable_enricher=True,
                    use_llm_fallback=getattr(Config, 'METADATA_USE_LLM_FALLBACK', False)
                )
            except ImportError:
                logger.warning("torrent_match not installed, identification disabled")
                self._matcher = False
        return self._matcher if self._matcher else None

    @property
    def media_metadata(self):
        """Lazy-load MediaMetadata."""
        if self._media_metadata is None:
            try:
                from media_metadata import MediaMetadata
                self._media_metadata = MediaMetadata()
            except ImportError:
                logger.warning("media_metadata not installed, enrichment disabled")
                self._media_metadata = False
        return self._media_metadata if self._media_metadata else None

    @property
    def jellyfin(self):
        """Lazy-load JellyfinFormatter."""
        if self._jellyfin is None:
            try:
                from media_metadata.jellyfin import JellyfinFormatter
                tmdb_key = getattr(Config, 'TMDB_API_KEY', None) or os.getenv('TMDB_API_KEY')
                self._jellyfin = JellyfinFormatter(tmdb_api_key=tmdb_key)
            except ImportError:
                logger.warning("media_metadata.jellyfin not available")
                self._jellyfin = False
        return self._jellyfin if self._jellyfin else None

    def identify_torrent(
        self,
        name: str,
        files: Optional[List[str]] = None
    ) -> IdentificationResult:
        """
        Identify media content from torrent name and files.

        Args:
            name: Torrent name
            files: Optional list of file paths in torrent

        Returns:
            IdentificationResult with media info and confidence
        """
        if not self.matcher:
            return IdentificationResult(
                success=False,
                error="torrent_match not available"
            )

        try:
            result = self.matcher.match(name, files=files, detail=True)

            if result is None:
                return IdentificationResult(
                    success=False,
                    error="No identification result"
                )

            # Handle both dict and object results
            if isinstance(result, dict):
                data = result
            else:
                data = result.to_dict(detail=True) if hasattr(result, 'to_dict') else {}

            # Build media_id from imdb_id or tmdb_id
            media_id = None
            imdb_id = data.get('imdb_id')
            tmdb_id = data.get('tmdb_id')
            media_type = data.get('media_type', 'unknown')

            if imdb_id:
                media_id = f"id:imdb:{imdb_id}"
            elif tmdb_id:
                # Include media type for TMDB IDs
                tmdb_type = 'movie' if media_type == 'movie' else 'tv'
                media_id = f"id:tmdb:{tmdb_type}:{tmdb_id}"

            confidence = data.get('confidence', 0.0)
            # Determine confidence level
            if confidence >= 0.85:
                confidence_level = "HIGH"
            elif confidence >= 0.70:
                confidence_level = "MEDIUM"
            elif confidence >= 0.50:
                confidence_level = "LOW"
            else:
                confidence_level = "VERY_LOW"

            return IdentificationResult(
                success=True,
                media_id=media_id,
                media_type=media_type,
                title=data.get('title'),
                year=data.get('year'),
                imdb_id=imdb_id,
                tmdb_id=tmdb_id,
                confidence=confidence,
                confidence_level=confidence_level,
                raw_result=data
            )

        except Exception as e:
            logger.error(f"Identification failed for '{name}': {e}")
            logger.debug(traceback.format_exc())
            return IdentificationResult(
                success=False,
                error=str(e)
            )

    def fetch_metadata(self, media_id: str) -> MetadataResult:
        """
        Fetch full metadata for an identified media item.

        Args:
            media_id: Standardized media ID (e.g., "id:imdb:tt0133093")

        Returns:
            MetadataResult with full metadata and artwork URLs
        """
        if not self.media_metadata:
            return MetadataResult(
                success=False,
                error="media_metadata not available"
            )

        try:
            metadata = self.media_metadata.get_metadata(media_id)

            if not metadata:
                return MetadataResult(
                    success=False,
                    error=f"No metadata found for {media_id}"
                )

            # Extract artwork URLs - check multiple possible locations
            TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/original"

            poster_url = metadata.get('poster_url') or metadata.get('image') or metadata.get('image_url')
            fanart_url = metadata.get('fanart_url') or metadata.get('backdrop')

            # Check tmdb_data for paths if no URLs found
            tmdb_data = metadata.get('tmdb_data', {})
            if not poster_url:
                poster_path = tmdb_data.get('poster_path')
                if poster_path:
                    poster_url = f"{TMDB_IMAGE_BASE}{poster_path}"

            if not fanart_url:
                backdrop_path = tmdb_data.get('backdrop_path')
                if backdrop_path:
                    fanart_url = f"{TMDB_IMAGE_BASE}{backdrop_path}"

            # Generate NFO content if jellyfin formatter available
            nfo_content = None
            if self.jellyfin and getattr(Config, 'METADATA_GENERATE_NFO', True):
                try:
                    nfo_content = self.jellyfin.generate_nfo(metadata)
                except Exception as e:
                    logger.warning(f"NFO generation failed: {e}")

            return MetadataResult(
                success=True,
                metadata=metadata,
                nfo_content=nfo_content,
                poster_url=poster_url,
                fanart_url=fanart_url
            )

        except Exception as e:
            logger.error(f"Metadata fetch failed for '{media_id}': {e}")
            logger.debug(traceback.format_exc())
            return MetadataResult(
                success=False,
                error=str(e)
            )

    async def write_metadata_files(
        self,
        server: TorrentServer,
        info_hash: str,
        identification: IdentificationResult,
        metadata: Optional[MetadataResult] = None
    ) -> List[str]:
        """
        Write metadata files to torrent directory.

        Writes to <download_dir>/<info_hash>/metadata/ on the server.
        Uses local mount if available, otherwise SSH/rsync.

        Args:
            server: TorrentServer to write to
            info_hash: Torrent info hash
            identification: Identification result
            metadata: Optional metadata result

        Returns:
            List of files written
        """
        files_written = []
        info_hash_lower = info_hash.lower()

        # Prepare file contents
        file_contents = {}

        # media.id - standardized media identifier
        if identification.media_id:
            file_contents['media.id'] = identification.media_id

        # identification.json - raw identification output
        ident_data = {
            'torrent_hash': info_hash,
            'result': identification.raw_result,
            'confidence': identification.confidence,
            'confidence_level': identification.confidence_level,
            'processed_at': datetime.now().isoformat()
        }
        file_contents['identification.json'] = json.dumps(ident_data, indent=2)

        # media.json - full metadata
        if metadata and metadata.success:
            meta_data = {
                'media_id': identification.media_id,
                'media_type': identification.media_type,
                'title': identification.title,
                'year': identification.year,
                'imdb_id': identification.imdb_id,
                'tmdb_id': identification.tmdb_id,
                'confidence': identification.confidence,
                'confidence_level': identification.confidence_level,
                'identified_at': datetime.now().isoformat(),
                **metadata.metadata
            }
            file_contents['media.json'] = json.dumps(meta_data, indent=2)

        # Determine write method based on server configuration
        if server.mount_path:
            metadata_dir = Path(server.mount_path) / info_hash_lower / "metadata"

            # Check if mount is accessible before attempting writes
            mount_accessible = True
            try:
                metadata_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.warning(f"Mount path not accessible: {e}")
                mount_accessible = False

            if mount_accessible:
                # Write basic files first
                files_written = await self._write_via_mount(
                    server, info_hash_lower, file_contents
                )

                # Use media_metadata to download NFO and artwork directly
                if identification.media_id and self.media_metadata:
                    try:
                        include_images = getattr(Config, 'METADATA_DOWNLOAD_ARTWORK', True)
                        success = self.media_metadata.download_metadata(
                            identification.media_id,
                            str(metadata_dir),
                            include_images=include_images
                        )
                        if success:
                            # Check what files were created
                            for fname in ['movie.nfo', 'tvshow.nfo', 'poster.jpg', 'fanart.jpg', 'cover.jpg']:
                                try:
                                    if (metadata_dir / fname).exists() and fname not in files_written:
                                        files_written.append(fname)
                                except OSError as e:
                                    logger.debug(f"Cannot check {fname} (mount unavailable): {e}")
                            logger.debug(f"Downloaded Jellyfin metadata to {metadata_dir}")
                    except OSError as e:
                        logger.warning(f"Mount unavailable for Jellyfin metadata download: {e}")
                    except Exception as e:
                        logger.warning(f"Failed to download Jellyfin metadata: {e}")

                # Always try to download artwork from identification data if not already present
                if getattr(Config, 'METADATA_DOWNLOAD_ARTWORK', True):
                    try:
                        # Check if artwork already exists (may fail if mount unavailable)
                        try:
                            poster_exists = (metadata_dir / "poster.jpg").exists()
                        except OSError:
                            poster_exists = False

                        try:
                            fanart_exists = (metadata_dir / "fanart.jpg").exists()
                        except OSError:
                            fanart_exists = False

                        if not poster_exists or not fanart_exists:
                            artwork_files = await self._download_artwork_mount(
                                server, info_hash_lower, metadata, identification
                            )
                            files_written.extend(artwork_files)
                    except OSError as e:
                        logger.warning(f"Mount unavailable for artwork download, skipping: {e}")

        elif server.ssh_host or server.host:
            # For SSH, write files then download artwork
            files_written = await self._write_via_ssh(
                server, info_hash_lower, file_contents
            )

            # Try to download artwork via SSH
            if metadata and getattr(Config, 'METADATA_DOWNLOAD_ARTWORK', True):
                artwork_files = await self._download_artwork_ssh(
                    server, info_hash_lower, metadata, identification
                )
                files_written.extend(artwork_files)

        return files_written

    async def _write_via_mount(
        self,
        server: TorrentServer,
        info_hash: str,
        file_contents: Dict[str, str]
    ) -> List[str]:
        """Write metadata files via local mount."""
        files_written = []

        try:
            metadata_dir = Path(server.mount_path) / info_hash / "metadata"
            metadata_dir.mkdir(parents=True, exist_ok=True)

            for filename, content in file_contents.items():
                file_path = metadata_dir / filename
                file_path.write_text(content)
                files_written.append(filename)
                logger.debug(f"Wrote {file_path}")

        except Exception as e:
            logger.error(f"Mount write failed: {e}")

        return files_written

    async def _write_via_ssh(
        self,
        server: TorrentServer,
        info_hash: str,
        file_contents: Dict[str, str]
    ) -> List[str]:
        """Write metadata files via SSH."""
        files_written = []

        ssh_host = server.ssh_host or server.host
        ssh_user = server.ssh_user or "root"
        ssh_port = server.ssh_port or 22

        remote_dir = f"{server.download_dir}/{info_hash}/metadata"

        # Build SSH command base
        ssh_base = ["ssh", "-p", str(ssh_port)]
        if server.ssh_key_path:
            ssh_base.extend(["-i", server.ssh_key_path])
        ssh_base.extend([
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "BatchMode=yes",
            f"{ssh_user}@{ssh_host}"
        ])

        try:
            # Create directory
            mkdir_cmd = ssh_base + [f"mkdir -p {shlex.quote(remote_dir)}"]
            process = await asyncio.create_subprocess_exec(
                *mkdir_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.wait()

            # Write each file
            for filename, content in file_contents.items():
                remote_path = f"{remote_dir}/{filename}"
                # Use cat with heredoc to write file
                write_cmd = ssh_base + [
                    f"cat > {shlex.quote(remote_path)}"
                ]
                process = await asyncio.create_subprocess_exec(
                    *write_cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate(input=content.encode())

                if process.returncode == 0:
                    files_written.append(filename)
                    logger.debug(f"Wrote {remote_path} via SSH")

        except Exception as e:
            logger.error(f"SSH write failed: {e}")

        return files_written

    async def _download_artwork_mount(
        self,
        server: TorrentServer,
        info_hash: str,
        metadata: Optional[MetadataResult],
        identification: Optional[IdentificationResult] = None
    ) -> List[str]:
        """Download artwork files via local mount."""
        import httpx

        TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/original"
        files_written = []
        metadata_dir = Path(server.mount_path) / info_hash / "metadata"

        # Build list of URLs to try for poster and fanart
        poster_urls = []
        fanart_urls = []

        if metadata and metadata.poster_url:
            poster_urls.append(metadata.poster_url)
        if metadata and metadata.fanart_url:
            fanart_urls.append(metadata.fanart_url)

        # Also check identification raw_result for TMDB paths
        if identification and identification.raw_result:
            detail = identification.raw_result.get('detail', {})
            poster_path = detail.get('poster_path')
            backdrop_path = detail.get('backdrop_path')
            if poster_path and not any(poster_path in u for u in poster_urls):
                poster_urls.append(f"{TMDB_IMAGE_BASE}{poster_path}")
            if backdrop_path and not any(backdrop_path in u for u in fanart_urls):
                fanart_urls.append(f"{TMDB_IMAGE_BASE}{backdrop_path}")

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                # Download poster
                poster_file = metadata_dir / "poster.jpg"
                try:
                    poster_exists = poster_file.exists()
                except OSError:
                    # Mount unavailable, skip poster download
                    poster_exists = True

                if not poster_exists:
                    for url in poster_urls:
                        try:
                            response = await client.get(url)
                            if response.status_code == 200 and len(response.content) > 1000:
                                poster_file.write_bytes(response.content)
                                files_written.append("poster.jpg")
                                logger.debug(f"Downloaded poster from {url}")
                                break
                        except Exception as e:
                            logger.debug(f"Poster download failed from {url}: {e}")

                # Download fanart
                fanart_file = metadata_dir / "fanart.jpg"
                try:
                    fanart_exists = fanart_file.exists()
                except OSError:
                    # Mount unavailable, skip fanart download
                    fanart_exists = True

                if not fanart_exists:
                    for url in fanart_urls:
                        try:
                            response = await client.get(url)
                            if response.status_code == 200 and len(response.content) > 1000:
                                fanart_file.write_bytes(response.content)
                                files_written.append("fanart.jpg")
                                logger.debug(f"Downloaded fanart from {url}")
                                break
                        except Exception as e:
                            logger.debug(f"Fanart download failed from {url}: {e}")
        except OSError as e:
            logger.warning(f"Mount unavailable for artwork download: {e}")

        return files_written

    async def _download_artwork_ssh(
        self,
        server: TorrentServer,
        info_hash: str,
        metadata: Optional[MetadataResult],
        identification: Optional[IdentificationResult] = None
    ) -> List[str]:
        """Download artwork files via SSH (curl on remote)."""
        TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/original"
        files_written = []

        ssh_host = server.ssh_host or server.host
        ssh_user = server.ssh_user or "root"
        ssh_port = server.ssh_port or 22
        remote_dir = f"{server.download_dir}/{info_hash}/metadata"

        ssh_base = ["ssh", "-p", str(ssh_port)]
        if server.ssh_key_path:
            ssh_base.extend(["-i", server.ssh_key_path])
        ssh_base.extend([
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "BatchMode=yes",
            f"{ssh_user}@{ssh_host}"
        ])

        # Build list of URLs to try
        poster_urls = []
        fanart_urls = []

        if metadata and metadata.poster_url:
            poster_urls.append(metadata.poster_url)
        if metadata and metadata.fanart_url:
            fanart_urls.append(metadata.fanart_url)

        # Also check identification raw_result for TMDB paths
        if identification and identification.raw_result:
            detail = identification.raw_result.get('detail', {})
            poster_path = detail.get('poster_path')
            backdrop_path = detail.get('backdrop_path')
            if poster_path:
                poster_urls.append(f"{TMDB_IMAGE_BASE}{poster_path}")
            if backdrop_path:
                fanart_urls.append(f"{TMDB_IMAGE_BASE}{backdrop_path}")

        # Download poster via curl on remote
        for url in poster_urls:
            try:
                remote_path = f"{remote_dir}/poster.jpg"
                curl_cmd = f"curl -sL -o {shlex.quote(remote_path)} {shlex.quote(url)}"
                cmd = ssh_base + [curl_cmd]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.wait()
                if process.returncode == 0:
                    files_written.append("poster.jpg")
                    break
            except Exception as e:
                logger.debug(f"Remote poster download failed from {url}: {e}")

        # Download fanart via curl on remote
        for url in fanart_urls:
            try:
                remote_path = f"{remote_dir}/fanart.jpg"
                curl_cmd = f"curl -sL -o {shlex.quote(remote_path)} {shlex.quote(url)}"
                cmd = ssh_base + [curl_cmd]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.wait()
                if process.returncode == 0:
                    files_written.append("fanart.jpg")
                    break
            except Exception as e:
                logger.debug(f"Remote fanart download failed from {url}: {e}")

        return files_written

    def _extract_media_id_from_labels(self, labels: Optional[List[str]]) -> Optional[str]:
        """
        Extract media ID from torrent labels if present.

        Looks for labels matching the media ID format: id:imdb:*, id:tmdb:*, etc.

        Args:
            labels: List of torrent labels

        Returns:
            Media ID string if found, None otherwise
        """
        if not labels:
            return None

        for label in labels:
            label = label.strip()
            # Check for standard media ID format
            if label.startswith("id:"):
                return label
            # Also check for bare IMDB IDs (tt followed by digits)
            if label.startswith("tt") and label[2:].isdigit():
                return f"id:imdb:{label}"

        return None

    def _build_identification_from_media_id(self, media_id: str) -> IdentificationResult:
        """
        Build an IdentificationResult from a known media ID.

        Fetches metadata to populate title, year, etc.

        Args:
            media_id: Standardized media ID (e.g., "id:imdb:tt0133093")

        Returns:
            IdentificationResult with full confidence
        """
        # Parse media_id for components
        parts = media_id.split(":")
        imdb_id = None
        tmdb_id = None
        media_type = "unknown"

        if len(parts) >= 3:
            if parts[1] == "imdb":
                imdb_id = parts[2]
                # Determine type from IMDB ID prefix or fetch from API
                media_type = "movie"  # Default, will be updated from metadata
            elif parts[1] == "tmdb" and len(parts) >= 4:
                media_type = parts[2]  # movie or tv
                try:
                    tmdb_id = int(parts[3])
                except ValueError:
                    pass

        # Try to fetch metadata to get title/year
        title = None
        year = None

        if self.media_metadata:
            try:
                metadata = self.media_metadata.get_metadata(media_id)
                if metadata:
                    title = metadata.get("title")
                    year = metadata.get("year")
                    media_type = metadata.get("media_type", media_type)
                    if not imdb_id:
                        imdb_id = metadata.get("imdb_id")
                    if not tmdb_id:
                        tmdb_id = metadata.get("tmdb_id")
            except Exception as e:
                logger.debug(f"Could not fetch metadata for {media_id}: {e}")

        return IdentificationResult(
            success=True,
            media_id=media_id,
            media_type=media_type,
            title=title,
            year=year,
            imdb_id=imdb_id,
            tmdb_id=tmdb_id,
            confidence=1.0,
            confidence_level="LABEL",
            raw_result={"source": "label", "media_id": media_id}
        )

    def _metadata_files_exist(self, server: TorrentServer, info_hash: str) -> bool:
        """
        Check if metadata files actually exist on disk.

        Args:
            server: TorrentServer to check
            info_hash: Torrent info hash

        Returns:
            True if key metadata files exist
        """
        if not server.mount_path:
            # Can't verify without mount path, assume they exist
            return True

        try:
            metadata_dir = Path(server.mount_path) / info_hash.lower() / "metadata"
            if not metadata_dir.exists():
                return False

            # Check for at least one key file
            key_files = ['media.id', 'identification.json', 'media.json']
            return any((metadata_dir / f).exists() for f in key_files)
        except OSError as e:
            # Mount unavailable, cannot verify - assume files don't exist
            logger.debug(f"Cannot verify metadata files (mount unavailable): {e}")
            return False

    async def process_torrent(
        self,
        torrent_hash: str,
        torrent_name: str,
        server: TorrentServer,
        files: Optional[List[str]] = None,
        labels: Optional[List[str]] = None,
        force: bool = False
    ) -> ProcessingResult:
        """
        Full metadata processing pipeline for a torrent.

        1. Check if already processed (unless force=True)
        2. Check labels for existing media ID
        3. If no label ID, identify media content from name/files
        4. Fetch full metadata if confidence sufficient
        5. Write metadata files to server
        6. Update database record

        Args:
            torrent_hash: Torrent info hash
            torrent_name: Torrent display name
            server: TorrentServer the torrent is on
            files: Optional list of files in torrent
            labels: Optional list of torrent labels (may contain media ID)
            force: Re-process even if already done

        Returns:
            ProcessingResult with full details
        """
        result = ProcessingResult(
            torrent_hash=torrent_hash,
            server_id=server.id
        )

        async with self._semaphore:
            try:
                # Check existing record
                existing = TorrentMetadata.get_or_none(
                    (TorrentMetadata.torrent_hash == torrent_hash.upper()) &
                    (TorrentMetadata.server_id == server.id)
                )

                # Only skip if status is completed AND files actually exist
                if existing and existing.status == "completed" and not force:
                    if self._metadata_files_exist(server, torrent_hash):
                        logger.debug(f"Already processed: {torrent_name}")
                        result.status = "skipped"
                        return result
                    else:
                        logger.info(f"Metadata files missing, re-processing: {torrent_name}")

                # Create or update record
                if not existing:
                    existing = TorrentMetadata.create(
                        torrent_hash=torrent_hash.upper(),
                        server_id=server.id,
                        status="processing"
                    )
                else:
                    existing.status = "processing"
                    existing.error = None
                    existing.save()

                # Step 1: Check labels for media ID first
                label_media_id = self._extract_media_id_from_labels(labels)
                if label_media_id:
                    logger.info(f"Using media ID from label: {label_media_id}")
                    identification = self._build_identification_from_media_id(label_media_id)
                else:
                    # Step 2: Identify from torrent name
                    logger.info(f"Identifying: {torrent_name}")
                    identification = self.identify_torrent(torrent_name, files)

                result.identification = identification

                if not identification.success:
                    existing.status = "failed"
                    existing.error = identification.error
                    existing.updated_at = datetime.now()
                    existing.save()
                    result.status = "failed"
                    result.error = identification.error
                    return result

                # Update record with identification
                existing.media_id = identification.media_id
                existing.media_type = identification.media_type
                existing.title = identification.title
                existing.year = identification.year
                existing.imdb_id = identification.imdb_id
                existing.tmdb_id = identification.tmdb_id
                existing.confidence = identification.confidence
                existing.confidence_level = identification.confidence_level
                existing.identified_at = datetime.now()
                existing.save()

                # Check confidence threshold
                min_confidence = getattr(Config, 'METADATA_MIN_CONFIDENCE', 0.7)
                if identification.confidence < min_confidence:
                    logger.info(
                        f"Low confidence ({identification.confidence:.2f}) for {torrent_name}, "
                        f"skipping metadata write"
                    )
                    existing.status = "low_confidence"
                    existing.updated_at = datetime.now()
                    existing.save()
                    result.status = "low_confidence"
                    return result

                # Step 2: Fetch metadata
                metadata = None
                if identification.media_id:
                    logger.info(f"Fetching metadata for {identification.media_id}")
                    metadata = self.fetch_metadata(identification.media_id)
                    result.metadata = metadata

                # Step 3: Write files
                files_written = await self.write_metadata_files(
                    server, torrent_hash, identification, metadata
                )
                result.files_written = files_written

                # Update final status
                existing.status = "completed"
                existing.metadata_written_at = datetime.now()
                existing.updated_at = datetime.now()
                existing.save()
                result.status = "completed"

                logger.info(
                    f"Processed {torrent_name}: {identification.title} "
                    f"({identification.year}) - {identification.confidence_level}"
                )

            except Exception as e:
                logger.error(f"Processing failed for {torrent_name}: {e}")
                logger.debug(traceback.format_exc())
                result.status = "failed"
                result.error = str(e)

                # Update database
                try:
                    existing = TorrentMetadata.get_or_none(
                        (TorrentMetadata.torrent_hash == torrent_hash.upper()) &
                        (TorrentMetadata.server_id == server.id)
                    )
                    if existing:
                        existing.status = "failed"
                        existing.error = str(e)[:500]
                        existing.updated_at = datetime.now()
                        existing.save()
                except Exception:
                    pass

        return result

    def queue_processing(
        self,
        torrent_hash: str,
        torrent_name: str,
        server: TorrentServer,
        files: Optional[List[str]] = None,
        labels: Optional[List[str]] = None
    ) -> None:
        """
        Queue a torrent for background processing.

        Creates a database record and schedules async processing.
        Does not block the caller.

        Args:
            torrent_hash: Torrent info hash
            torrent_name: Torrent display name
            server: TorrentServer the torrent is on
            files: Optional list of files in torrent
            labels: Optional list of torrent labels (may contain media ID)
        """
        # Create pending record
        torrent_hash_upper = torrent_hash.upper()
        existing = TorrentMetadata.get_or_none(
            (TorrentMetadata.torrent_hash == torrent_hash_upper) &
            (TorrentMetadata.server_id == server.id)
        )

        # Skip if already processing
        if existing and existing.status == "processing":
            logger.debug(f"Already processing: {torrent_name}")
            return

        # Skip if completed AND files actually exist
        if existing and existing.status == "completed":
            if self._metadata_files_exist(server, torrent_hash):
                logger.debug(f"Already queued/processed: {torrent_name}")
                return
            else:
                logger.info(f"Metadata files missing, re-queuing: {torrent_name}")
                # Reset status so it gets re-processed
                existing.status = "pending"
                existing.save()

        if not existing:
            TorrentMetadata.create(
                torrent_hash=torrent_hash_upper,
                server_id=server.id,
                status="pending"
            )

        # Schedule background task
        task_key = f"{server.id}:{torrent_hash_upper}"
        if task_key not in self._task_queue:
            task = asyncio.create_task(
                self.process_torrent(torrent_hash, torrent_name, server, files, labels)
            )
            self._task_queue[task_key] = task

            def cleanup(t, key=task_key):
                self._task_queue.pop(key, None)

            task.add_done_callback(cleanup)

    def get_status(self, torrent_hash: str, server_id: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata status for a torrent.

        Args:
            torrent_hash: Torrent info hash
            server_id: Server ID

        Returns:
            Dict with status info or None
        """
        record = TorrentMetadata.get_or_none(
            (TorrentMetadata.torrent_hash == torrent_hash.upper()) &
            (TorrentMetadata.server_id == server_id)
        )

        if not record:
            return None

        return {
            "torrent_hash": record.torrent_hash,
            "server_id": record.server_id,
            "status": record.status,
            "media_id": record.media_id,
            "media_type": record.media_type,
            "title": record.title,
            "year": record.year,
            "imdb_id": record.imdb_id,
            "tmdb_id": record.tmdb_id,
            "confidence": record.confidence,
            "confidence_level": record.confidence_level,
            "error": record.error,
            "identified_at": record.identified_at.isoformat() if record.identified_at else None,
            "metadata_written_at": record.metadata_written_at.isoformat() if record.metadata_written_at else None,
        }


# Global service instance
_metadata_service: Optional[MetadataService] = None


def get_metadata_service() -> MetadataService:
    """Get the global metadata service instance."""
    global _metadata_service
    if _metadata_service is None:
        _metadata_service = MetadataService()
    return _metadata_service
