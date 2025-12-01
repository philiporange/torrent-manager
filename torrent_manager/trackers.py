"""
Public tracker list caching and augmentation.

Fetches a list of public trackers from a configurable URL on startup,
caching them for use when adding public torrents. This helps speed up
peer discovery for non-private torrents.
"""

import httpx

from .config import Config
from .logger import logger


_cached_trackers: list[str] = []


async def fetch_trackers() -> list[str]:
    """
    Fetch the public tracker list from the configured URL.

    Returns a list of tracker URLs, filtering out empty lines.
    """
    global _cached_trackers

    if not Config.AUGMENT_TRACKERS:
        logger.info("Tracker augmentation disabled")
        return []

    url = Config.TRACKERS_LIST_URL
    logger.info(f"Fetching public tracker list from {url}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            lines = response.text.strip().split('\n')
            trackers = [line.strip() for line in lines if line.strip()]

            _cached_trackers = trackers
            logger.info(f"Cached {len(trackers)} public trackers")
            return trackers

    except httpx.HTTPError as e:
        logger.warning(f"Failed to fetch tracker list: {e}")
        return []
    except Exception as e:
        logger.warning(f"Error fetching tracker list: {e}")
        return []


def get_cached_trackers() -> list[str]:
    """Return the cached list of public trackers."""
    return _cached_trackers.copy()


def is_augmentation_enabled() -> bool:
    """Check if tracker augmentation is enabled."""
    return Config.AUGMENT_TRACKERS and len(_cached_trackers) > 0
