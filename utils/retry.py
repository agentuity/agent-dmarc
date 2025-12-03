import asyncio
from typing import TypeVar, Callable
from functools import wraps
import logging

T = TypeVar('T')

def async_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    exponential_base: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Decorator for async functions with exponential backoff retry.

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        base_delay: Base delay in seconds before first retry (default: 1.0)
        exponential_base: Exponential base for backoff calculation (default: 2.0)
        exceptions: Tuple of exception types to catch and retry (default: (Exception,))

    Returns:
        Decorated async function with retry logic

    Example:
        @async_retry(max_attempts=3, exceptions=(APIError, TimeoutError))
        async def call_api():
            return await api.fetch()
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            logger = logging.getLogger(func.__name__)
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts - 1:
                        logger.error(f"All {max_attempts} attempts failed: {e}")
                        raise
                    delay = base_delay * (exponential_base ** attempt)
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
        return wrapper
    return decorator
