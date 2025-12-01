import os
import tempfile
import dotenv


dotenv.load_dotenv()


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
SEEDING_CHECK_INTERVAL = 300           # Check interval in seconds (5 minutes)

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
