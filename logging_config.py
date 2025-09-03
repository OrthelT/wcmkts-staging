import logging
from logging.handlers import RotatingFileHandler

def setup_logging(name="app", log_file="wcmkts_app.log", level=logging.INFO, max_bytes=5*1024*1024, backup_count=3):
    """Set up logging configuration with a rotating file handler and a stream handler.

    Args:
        name: The name of the logger.
        log_file: The name of the log file.
        level: The level of the logger.
        max_bytes: The maximum size of the log file.
        backup_count: The number of backup log files.

    Returns:
        logger: The logger object.

    Example usage:
    from logging_config import setup_logging
    setup_logging()
    """
    logger = logging.getLogger(name)
    # Clear existing handlers to avoid duplicate logs
    if logger.hasHandlers():
        logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter("%(asctime)s %(levelname)-8s "
                                    "[%(filename)s:%(lineno)d %(funcName)s()] "
                                    "%(message)s")

    # Create and add rotating file handler
    file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Create and add stream handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    logger.setLevel(level)
    return logger