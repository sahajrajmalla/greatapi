import functools
import sys
import time

from config import settings
from loguru import logger


def logger_wraps(*, entry=True, exit=True, level="DEBUG"):
    def wrapper(func):
        name = func.__name__

        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            logger_ = logger.opt(depth=1)
            if entry:
                logger_.log(level, "Entering '{}' (args={}, kwargs={})", name, args, kwargs)
            result = func(*args, **kwargs)
            if exit:
                logger_.log(level, "Exiting '{}' (result={})", name, result)
            return result

        return wrapped

    return wrapper


def timeit(func):
    def wrapped(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        logger.debug("Function '{}' executed in {:f} s", func.__name__, end - start)
        return result

    return wrapped


def set_local_logger():
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        # serialize=True,
        backtrace=True,
        diagnose=True,
    )
    return logger


def set_dev_logger():
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
    )
    return logger


def init_logger():
    """
    Initializes the logger according to set environment.
    """
    logger_map = {
        "local": set_local_logger,
        "dev": set_dev_logger,
        "default": set_local_logger,
    }
    return logger_map.get(settings.ENV_FOR_DYNACONF, "default").__call__()
