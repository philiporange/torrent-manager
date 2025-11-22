from loguru import logger

from .config import Config


VERBOSE = Config.VERBOSE
LOG_PATH = Config.LOG_PATH
LOG_LEVEL = Config.LOG_LEVEL
LOG_ROTATION = Config.LOG_ROTATION
LOG_RETENTION = Config.LOG_RETENTION


# Log to a file
logger.add(
    LOG_PATH,
    rotation="1 week",
    retention="1 month",
    level=LOG_LEVEL,
)

# Log to console
if VERBOSE:
    logger.add(
        sink=None,
        level=LOG_LEVEL,
    )