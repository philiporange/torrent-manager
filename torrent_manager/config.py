"""Configuration management with environment variable overrides.

Defines default configuration values at module level and exposes a Config class
that loads values from environment variables (from ~/.env and project .env).
All configuration options can be overridden via environment variables.
"""

import os
import tempfile
import dotenv


# Load environment from multiple locations (later files override earlier)
dotenv.load_dotenv(os.path.expanduser("~/.env"))  # Global user config
dotenv.load_dotenv()  # Project .env


# Defaults
DEBUG = True
VERBOSE = False
LOG_PATH = "rtorrent_manager.log"
LOG_LEVEL = "DEBUG" if DEBUG else "INFO"
LOG_ROTATION = "1 week"
LOG_RETENTION = "1 month"
DB_PATH = "activity_logs.db"
CONFIG_PATH = os.path.expanduser("~/.rtorrent_manager.conf")

HOME = os.getenv("HOME")
INCOMPLETE_DIR = "downloads"
INCOMPLETE_PATH = os.path.join(HOME, INCOMPLETE_DIR)
COMPLETE_DIR = "complete"
COMPLETE_PATH = os.path.join(HOME, COMPLETE_DIR)
MAX_INTERVAL = 300

# Seeding duration settings (in seconds)
PUBLIC_SEED_DURATION = 0
PRIVATE_SEED_DURATION = 7 * 24 * 3600  # 7 days for private torrents
AUTO_PAUSE_SEEDING = True              # Enable/disable auto-pause feature
SEEDING_CHECK_INTERVAL = 60            # Check interval in seconds (1 minute)

# Server polling intervals (in seconds)
POLL_SERVER_IDLE_INTERVAL = 60         # Poll servers every 60s when idle
POLL_SERVER_ACTIVE_INTERVAL = 15       # Poll servers every 15s when downloads active

RTORRENT_RPC_URL = "http://localhost:9080/RPC2"

# Transmission defaults
TRANSMISSION_HOST = "localhost"
TRANSMISSION_PORT = 9091
TRANSMISSION_USERNAME = ""
TRANSMISSION_PASSWORD = ""

SQLITE_DB_PATH = tempfile.NamedTemporaryFile().name
REDISLITE_DB_PATH = tempfile.NamedTemporaryFile().name

CONTAINER_NAME = "rtorrent-manager"

# Tracker augmentation for public torrents
TRACKERS_LIST_URL = "https://raw.githubusercontent.com/ngosang/trackerslist/refs/heads/master/trackers_best.txt"
AUGMENT_TRACKERS = True

# Magnet resolver settings (uses magnet2torrent to convert magnets to .torrent files)
MAGNET_RESOLVER_ENABLED = True
MAGNET_RESOLVER_TIMEOUT = 300
MAGNET_RESOLVER_ENABLE_DHT = False
MAGNET_RESOLVER_PROXY_HOST = None
MAGNET_RESOLVER_PROXY_PORT = None
MAGNET_RESOLVER_HTTP_PROXY = None

# Transfer service settings (auto-download completed torrents via rsync)
TRANSFER_MAX_CONCURRENT = 2   # Maximum concurrent transfers
TRANSFER_MAX_RETRIES = 3      # Max retries on failure

# RSS polling settings
RSS_POLL_INTERVAL = 300       # Check RSS feeds every 5 minutes
RSS_RETRY_DELAY = 900         # Retry failed RSS adds after 15 minutes
RSS_429_BACKOFF_BASE = 1800   # First 429 retry waits 30 minutes
RSS_429_BACKOFF_MULTIPLIER = 2
RSS_429_BACKOFF_MAX = 21600   # Cap 429 retry backoff at 6 hours

# Remote torrent file download throttling
TORRENT_URL_MIN_INTERVAL = 5  # Minimum seconds between HTTP .torrent fetches per host
RSS_RATE_LIMIT_DELAY = 2.0    # Delay between processing RSS items (seconds)
RSS_MAX_ITEMS_PER_CYCLE = 50  # Maximum RSS items to process per cycle

# Client timeout settings (in seconds)
CLIENT_TIMEOUT = 30           # Default timeout for torrent client operations
MONITOR_TIMEOUT = 30          # Timeout for background monitoring tasks

# Callback settings (lifecycle hooks for torrents)
CALLBACK_DIR = os.path.expanduser("~/.torrent_manager/callbacks")

# Metadata service settings (automatic media identification)
METADATA_AUTO_IDENTIFY = True         # Enable automatic identification on torrent add
METADATA_MIN_CONFIDENCE = 0.7         # Minimum confidence to write metadata files
METADATA_DOWNLOAD_ARTWORK = True      # Download poster/fanart images
METADATA_GENERATE_NFO = True          # Generate Jellyfin NFO files
METADATA_USE_LLM_FALLBACK = False     # Use LLM for low-confidence identifications
TMDB_API_KEY = None                   # TMDB API key for metadata enrichment


class Config:
    DEBUG = os.getenv("DEBUG", DEBUG)
    VERBOSE = os.getenv("VERBOSE", VERBOSE)

    LOG_PATH = os.getenv("LOG_PATH", LOG_PATH)
    LOG_LEVEL = os.getenv("LOG_LEVEL", LOG_LEVEL)
    LOG_ROTATION = os.getenv("LOG_ROTATION", LOG_ROTATION)
    LOG_RETENTION = os.getenv("LOG_RETENTION", LOG_RETENTION)

    DB_PATH = os.getenv("DB_PATH", DB_PATH)
    CONFIG_PATH = os.getenv("CONFIG_PATH", CONFIG_PATH)

    INCOMPLETE_PATH = os.getenv("INCOMPLETE_PATH", INCOMPLETE_PATH)
    COMPLETE_PATH = os.getenv("COMPLETE_PATH", COMPLETE_PATH)
    MAX_INTERVAL = int(os.getenv("MAX_INTERVAL", MAX_INTERVAL))

    # Seeding duration settings
    PUBLIC_SEED_DURATION = int(os.getenv("PUBLIC_SEED_DURATION", PUBLIC_SEED_DURATION))
    PRIVATE_SEED_DURATION = int(os.getenv("PRIVATE_SEED_DURATION", PRIVATE_SEED_DURATION))
    AUTO_PAUSE_SEEDING = os.getenv("AUTO_PAUSE_SEEDING", str(AUTO_PAUSE_SEEDING)).lower() == "true"
    SEEDING_CHECK_INTERVAL = int(os.getenv("SEEDING_CHECK_INTERVAL", SEEDING_CHECK_INTERVAL))

    # Server polling intervals
    POLL_SERVER_IDLE_INTERVAL = int(os.getenv("POLL_SERVER_IDLE_INTERVAL", POLL_SERVER_IDLE_INTERVAL))
    POLL_SERVER_ACTIVE_INTERVAL = int(os.getenv("POLL_SERVER_ACTIVE_INTERVAL", POLL_SERVER_ACTIVE_INTERVAL))

    RTORRENT_RPC_URL = os.getenv("RTORRENT_RPC_URL", RTORRENT_RPC_URL)

    # Transmission Configuration
    TRANSMISSION_HOST = os.getenv("TRANSMISSION_HOST", TRANSMISSION_HOST)
    TRANSMISSION_PORT = int(os.getenv("TRANSMISSION_PORT", TRANSMISSION_PORT))
    TRANSMISSION_USERNAME = os.getenv("TRANSMISSION_USERNAME", TRANSMISSION_USERNAME)
    TRANSMISSION_PASSWORD = os.getenv("TRANSMISSION_PASSWORD", TRANSMISSION_PASSWORD)

    SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", SQLITE_DB_PATH)
    REDISLITE_DB_PATH = os.getenv("REDISLITE_DB_PATH", REDISLITE_DB_PATH)

    CONTAINER_NAME = os.getenv("CONTAINER_NAME", CONTAINER_NAME)

    # API Configuration
    API_HOST = os.getenv("API_HOST", "localhost")
    API_PORT = int(os.getenv("API_PORT", "8144"))
    API_BASE_PATH = os.getenv("API_BASE_PATH", "").rstrip('/')

    # Server Configuration
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8144"))

    # Security Configuration
    # Default to False for local HTTP development. Set COOKIE_SECURE=true in production with HTTPS.
    COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

    # Tracker augmentation for public torrents
    TRACKERS_LIST_URL = os.getenv("TRACKERS_LIST_URL", TRACKERS_LIST_URL)
    AUGMENT_TRACKERS = os.getenv("AUGMENT_TRACKERS", str(AUGMENT_TRACKERS)).lower() == "true"

    # Magnet resolver settings
    MAGNET_RESOLVER_ENABLED = os.getenv("MAGNET_RESOLVER_ENABLED", str(MAGNET_RESOLVER_ENABLED)).lower() == "true"
    MAGNET_RESOLVER_TIMEOUT = int(os.getenv("MAGNET_RESOLVER_TIMEOUT", str(MAGNET_RESOLVER_TIMEOUT)))
    MAGNET_RESOLVER_ENABLE_DHT = os.getenv("MAGNET_RESOLVER_ENABLE_DHT", str(MAGNET_RESOLVER_ENABLE_DHT)).lower() == "true"
    MAGNET_RESOLVER_PROXY_HOST = os.getenv("MAGNET_RESOLVER_PROXY_HOST", MAGNET_RESOLVER_PROXY_HOST)
    MAGNET_RESOLVER_PROXY_PORT = int(os.getenv("MAGNET_RESOLVER_PROXY_PORT", "0")) or MAGNET_RESOLVER_PROXY_PORT
    MAGNET_RESOLVER_HTTP_PROXY = os.getenv("MAGNET_RESOLVER_HTTP_PROXY", MAGNET_RESOLVER_HTTP_PROXY)

    # Transfer service settings
    TRANSFER_MAX_CONCURRENT = int(os.getenv("TRANSFER_MAX_CONCURRENT", str(TRANSFER_MAX_CONCURRENT)))
    TRANSFER_MAX_RETRIES = int(os.getenv("TRANSFER_MAX_RETRIES", str(TRANSFER_MAX_RETRIES)))

    # RSS polling settings
    RSS_POLL_INTERVAL = int(os.getenv("RSS_POLL_INTERVAL", str(RSS_POLL_INTERVAL)))
    RSS_RETRY_DELAY = int(os.getenv("RSS_RETRY_DELAY", str(RSS_RETRY_DELAY)))
    RSS_429_BACKOFF_BASE = int(os.getenv("RSS_429_BACKOFF_BASE", str(RSS_429_BACKOFF_BASE)))
    RSS_429_BACKOFF_MULTIPLIER = int(os.getenv("RSS_429_BACKOFF_MULTIPLIER", str(RSS_429_BACKOFF_MULTIPLIER)))
    RSS_429_BACKOFF_MAX = int(os.getenv("RSS_429_BACKOFF_MAX", str(RSS_429_BACKOFF_MAX)))
    RSS_RATE_LIMIT_DELAY = float(os.getenv("RSS_RATE_LIMIT_DELAY", str(RSS_RATE_LIMIT_DELAY)))
    RSS_MAX_ITEMS_PER_CYCLE = int(os.getenv("RSS_MAX_ITEMS_PER_CYCLE", str(RSS_MAX_ITEMS_PER_CYCLE)))

    # Remote torrent file download throttling
    TORRENT_URL_MIN_INTERVAL = int(os.getenv("TORRENT_URL_MIN_INTERVAL", str(TORRENT_URL_MIN_INTERVAL)))

    # Client timeout settings
    CLIENT_TIMEOUT = int(os.getenv("CLIENT_TIMEOUT", str(CLIENT_TIMEOUT)))
    MONITOR_TIMEOUT = int(os.getenv("MONITOR_TIMEOUT", str(MONITOR_TIMEOUT)))

    # Callback settings
    CALLBACK_DIR = os.getenv("CALLBACK_DIR", CALLBACK_DIR)

    # Metadata service settings
    METADATA_AUTO_IDENTIFY = os.getenv("METADATA_AUTO_IDENTIFY", str(METADATA_AUTO_IDENTIFY)).lower() == "true"
    METADATA_MIN_CONFIDENCE = float(os.getenv("METADATA_MIN_CONFIDENCE", str(METADATA_MIN_CONFIDENCE)))
    METADATA_DOWNLOAD_ARTWORK = os.getenv("METADATA_DOWNLOAD_ARTWORK", str(METADATA_DOWNLOAD_ARTWORK)).lower() == "true"
    METADATA_GENERATE_NFO = os.getenv("METADATA_GENERATE_NFO", str(METADATA_GENERATE_NFO)).lower() == "true"
    METADATA_USE_LLM_FALLBACK = os.getenv("METADATA_USE_LLM_FALLBACK", str(METADATA_USE_LLM_FALLBACK)).lower() == "true"
    TMDB_API_KEY = os.getenv("TMDB_API_KEY", TMDB_API_KEY)

    @property
    def API_BASE_URL(self):
        """Construct the full API base URL."""
        base = f"http://{self.API_HOST}:{self.API_PORT}"
        if self.API_BASE_PATH:
            base += f"/{self.API_BASE_PATH}"
        return base


class TestConfig:
    CONTAINER_NAME = "rtorrent-manager-test"
    
    LOG_PATH = tempfile.NamedTemporaryFile().name
    DB_PATH = tempfile.NamedTemporaryFile().name
    
    SQLITE_DB_PATH = tempfile.NamedTemporaryFile().name
    REDISLITE_DB_PATH = tempfile.NamedTemporaryFile().name
