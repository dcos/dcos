"""Panda package management for Windows.

Logging instrumentation.
"""
import logging
import logging.handlers as loghandlers
import time


class LOG_LEVEL:
    """Log level constants."""
    CRITICAL = logging.CRITICAL
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    INFO = logging.INFO
    DEBUG = logging.DEBUG
    NOTSET = logging.NOTSET


def get_logger(name):
    """Instantiate a regular module-level logger.

    :param name: str, logger name
    :return:     logging.Logger, logger
    """
    return logging.getLogger(name=name)


def master_setup(log_level, file_path, file_size, history_size):
    """Setup the master part of logging infrastructure.

    :param log_level:         int, log-level constant (ex. logging.INFO)
    :param file_path:         pathlib.Path, local FS path to the log-file
    :param file_size:         int, maximum size (bytes) of a single log-file
                              before it gets rotated
    :param history_size:      int, maximum size of log-file history. The oldest
                              file is dropped when history reaches this number
                              of log-files and rotation is on.
    """
    # Setup log formatter
    if log_level == LOG_LEVEL.DEBUG:
        log_fmt = logging.Formatter(
            '%(asctime)s %(processName)s (%(process)d):'
            ' %(threadName)s (%(thread)d): %(name)s:'
            ' %(levelname)s: %(message)s'
        )
    else:
        log_fmt = logging.Formatter(
            '%(asctime)s %(processName)s (%(process)d):'
            ' %(levelname)s: %(message)s'
        )
    # Use UTC-based timestamps in log
    log_fmt.converter = time.gmtime
    # Suppress error reporting during logging operations
    logging.raiseExceptions = False
    # Setup log handler
    rf_handler = loghandlers.RotatingFileHandler(
        filename=file_path, maxBytes=file_size, backupCount=history_size
    )
    rf_handler.setFormatter(log_fmt)
    # Setup root logger
    root_logger = logging.getLogger('')
    root_logger.setLevel(log_level)
    root_logger.addHandler(rf_handler)
