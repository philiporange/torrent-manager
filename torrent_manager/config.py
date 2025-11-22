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
MIN_SEEDING_DURATION = 24 * 3600
MAX_INTERVAL = 300

RTORRENT_RPC_URL = "http://localhost:9080/RPC2"

SQLITE_DB_PATH = tempfile.NamedTemporaryFile().name
REDISLITE_DB_PATH = tempfile.NamedTemporaryFile().name

CONTAINER_NAME = "rtorrent-manager"


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
    MIN_SEEDING_DURATION = int(os.getenv("MIN_SEEDING_DURATION", MIN_SEEDING_DURATION))
    MAX_INTERVAL = int(os.getenv("MAX_INTERVAL", MAX_INTERVAL))

    RTORRENT_RPC_URL = os.getenv("RTORRENT_RPC_URL", RTORRENT_RPC_URL)

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
