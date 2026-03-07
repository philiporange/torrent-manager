"""
RSS automation for discovering and enqueueing torrent adds.

The service polls configured RSS/Atom feeds on a fixed interval, extracts torrent
URIs from feed items, deduplicates them per user, and waits until each item's
scheduled add time before sending it through the shared torrent add pipeline.
Rate limiting is applied between item processing to reduce tracker pressure, and
HTTP 429 errors trigger exponential retry backoff so private trackers are not
hammered after they begin rate limiting requests.

Database connection management ensures the SQLite connection is open before
database operations. Query results are eagerly evaluated with list() to prevent
lazy iteration errors when the connection is closed by other async tasks between
the query and iteration.
"""

import asyncio
import datetime
import email.utils
import secrets
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

import httpx

from .config import Config
from .dbs import sdb as db
from .logger import logger
from .models import RSSFeed, RSSFeedItem, TorrentServer
from .torrent_adder import add_torrent_to_server, is_info_hash

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


class RSSService:
    """Background service for feed refresh and delayed torrent adds."""

    def __init__(self) -> None:
        self._running = False

    def _ensure_db_connected(self) -> None:
        """Ensure database connection is open before operations."""
        if db.is_closed():
            db.connect(reuse_if_open=True)

    async def _fetch_feed_content(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=Config.CLIENT_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime.datetime]:
        if not value:
            return None
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            if parsed.tzinfo is not None:
                return parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            return parsed
        except Exception:
            return None

    def _extract_uri(self, entry: ET.Element, is_atom: bool) -> tuple[Optional[str], Optional[str], Optional[str]]:
        if is_atom:
            title = entry.findtext("atom:title", namespaces=ATOM_NS)
            guid = entry.findtext("atom:id", namespaces=ATOM_NS)
            links = entry.findall("atom:link", namespaces=ATOM_NS)
            candidates = []
            link_href = None
            for link in links:
                href = link.get("href")
                rel = (link.get("rel") or "alternate").lower()
                type_hint = (link.get("type") or "").lower()
                if href:
                    if rel == "enclosure" or "bittorrent" in type_hint:
                        candidates.insert(0, href)
                    else:
                        candidates.append(href)
                    if not link_href and rel == "alternate":
                        link_href = href
            for candidate in candidates:
                if self._is_supported_uri(candidate):
                    return title, guid, candidate
            return title, guid, link_href if self._is_supported_uri(link_href) else None

        title = entry.findtext("title")
        guid = entry.findtext("guid")
        link_text = entry.findtext("link")
        enclosure = entry.find("enclosure")
        candidates = []
        if enclosure is not None and enclosure.get("url"):
            candidates.append(enclosure.get("url"))
        if link_text:
            candidates.append(link_text)
        if guid:
            candidates.append(guid)
        for candidate in candidates:
            if self._is_supported_uri(candidate):
                return title, guid, candidate
        return title, guid, None

    def _is_supported_uri(self, value: Optional[str]) -> bool:
        if not value:
            return False
        value = value.strip()
        return value.startswith("magnet:") or value.startswith("http://") or value.startswith("https://") or is_info_hash(value)

    def _fingerprint_for(self, guid: Optional[str], uri: str) -> str:
        key = (guid or uri or "").strip()
        if key.startswith("magnet:?xt=urn:btih:"):
            key = key.split(":")[-1]
        return key.upper() if is_info_hash(key) else key

    def _entry_info_hash(self, uri: str) -> Optional[str]:
        uri = uri.strip()
        if is_info_hash(uri):
            return uri.upper()
        if uri.startswith("magnet:") and "btih:" in uri.lower():
            return uri.rsplit(":", 1)[-1].split("&", 1)[0].upper()
        return None

    def _parse_feed_entries(self, xml_text: str) -> List[Dict[str, Optional[str]]]:
        root = ET.fromstring(xml_text)
        is_atom = root.tag.endswith("feed")
        entries: List[Dict[str, Optional[str]]] = []

        if is_atom:
            iter_entries = root.findall("atom:entry", namespaces=ATOM_NS)
        else:
            channel = root.find("channel")
            iter_entries = [] if channel is None else channel.findall("item")

        for entry in iter_entries:
            title, guid, uri = self._extract_uri(entry, is_atom)
            if not uri:
                continue
            published = None
            if is_atom:
                published = (
                    entry.findtext("atom:published", namespaces=ATOM_NS)
                    or entry.findtext("atom:updated", namespaces=ATOM_NS)
                )
            else:
                published = entry.findtext("pubDate")
            entries.append(
                {
                    "title": title or uri,
                    "guid": guid,
                    "uri": uri.strip(),
                    "published_at": self._parse_datetime(published),
                    "info_hash": self._entry_info_hash(uri),
                }
            )
        return entries

    def _is_rate_limited_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return "429" in message or "too many requests" in message

    def _retry_delay_for(self, exc: Exception, attempt_count: int) -> int:
        if not self._is_rate_limited_error(exc):
            return Config.RSS_RETRY_DELAY

        step = max(0, attempt_count - 1)
        delay = Config.RSS_429_BACKOFF_BASE * (Config.RSS_429_BACKOFF_MULTIPLIER ** step)
        return min(int(delay), Config.RSS_429_BACKOFF_MAX)

    async def refresh_feed(self, feed: RSSFeed) -> int:
        """Refresh a single feed and store any newly detected items."""
        self._ensure_db_connected()
        now = datetime.datetime.now()
        created = 0
        try:
            xml_text = await self._fetch_feed_content(feed.url)
            entries = self._parse_feed_entries(xml_text)
            for entry in entries:
                fingerprint = self._fingerprint_for(entry["guid"], entry["uri"])
                exists = RSSFeedItem.select().where(
                    (RSSFeedItem.user_id == feed.user_id)
                    & (RSSFeedItem.fingerprint == fingerprint)
                ).exists()
                if exists:
                    continue

                detected_at = entry["published_at"] or now
                next_attempt_at = max(
                    now,
                    detected_at + datetime.timedelta(hours=max(feed.delay_hours, 0)),
                )
                RSSFeedItem.create(
                    id=secrets.token_urlsafe(16),
                    feed_id=feed.id,
                    user_id=feed.user_id,
                    server_id=feed.server_id,
                    title=entry["title"],
                    guid=entry["guid"],
                    link=entry["uri"],
                    uri=entry["uri"],
                    fingerprint=fingerprint,
                    info_hash=entry["info_hash"],
                    status="pending",
                    detected_at=detected_at,
                    next_attempt_at=next_attempt_at,
                )
                created += 1

            feed.last_checked_at = now
            feed.last_success_at = now
            feed.last_error = None
            feed.last_item_count = len(entries)
            feed.save()
        except Exception as exc:
            feed.last_checked_at = now
            feed.last_error = str(exc)
            feed.save()
            logger.error(f"Failed to refresh RSS feed {feed.name}: {exc}")
        return created

    async def refresh_enabled_feeds(self) -> None:
        """Refresh all enabled feeds sequentially."""
        self._ensure_db_connected()
        feeds = list(RSSFeed.select().where(RSSFeed.enabled == True))
        for feed in feeds:
            await self.refresh_feed(feed)

    async def process_pending_items(self) -> None:
        """Add any detected items whose delay window has elapsed."""
        self._ensure_db_connected()
        now = datetime.datetime.now()
        pending_items = list(RSSFeedItem.select().where(
            (RSSFeedItem.status == "pending")
            & (RSSFeedItem.next_attempt_at <= now)
        ).order_by(RSSFeedItem.next_attempt_at.asc()).limit(Config.RSS_MAX_ITEMS_PER_CYCLE))

        for idx, item in enumerate(pending_items):
            if idx > 0 and Config.RSS_RATE_LIMIT_DELAY > 0:
                await asyncio.sleep(Config.RSS_RATE_LIMIT_DELAY)

            self._ensure_db_connected()
            try:
                server = TorrentServer.get(TorrentServer.id == item.server_id)
            except TorrentServer.DoesNotExist:
                item.last_error = "Target server no longer exists"
                item.attempt_count += 1
                item.next_attempt_at = now + datetime.timedelta(seconds=Config.RSS_RETRY_DELAY)
                item.save()
                continue

            if not server.enabled:
                item.last_error = "Target server is disabled"
                item.attempt_count += 1
                item.next_attempt_at = now + datetime.timedelta(seconds=Config.RSS_RETRY_DELAY)
                item.save()
                continue

            try:
                await add_torrent_to_server(server, item.uri, user_id=item.user_id)
                item.status = "added"
                item.added_at = datetime.datetime.now()
                item.last_error = None
                item.attempt_count += 1
                item.save()
            except Exception as exc:
                item.last_error = str(exc)
                item.attempt_count += 1
                delay_seconds = self._retry_delay_for(exc, item.attempt_count)
                item.next_attempt_at = now + datetime.timedelta(seconds=delay_seconds)
                item.save()
                logger.error(f"Failed to add RSS item {item.title}: {exc}")

    async def run(self) -> None:
        """Main RSS polling loop."""
        self._running = True
        logger.info(f"RSS service started (interval: {Config.RSS_POLL_INTERVAL}s)")

        while self._running:
            try:
                await self.refresh_enabled_feeds()
                await self.process_pending_items()
                await asyncio.sleep(Config.RSS_POLL_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in RSS service loop: {exc}")
                await asyncio.sleep(Config.RSS_POLL_INTERVAL)

        logger.info("RSS service stopped")

    def stop(self) -> None:
        self._running = False


_rss_service: Optional[RSSService] = None


def get_rss_service() -> RSSService:
    """Get the global RSS service instance."""
    global _rss_service
    if _rss_service is None:
        _rss_service = RSSService()
    return _rss_service
