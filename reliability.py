"""Retry helpers for flaky network / external-API operations.

The video pipeline depends on remote services (Leonardo image + motion, TTS,
uploads) that fail transiently. A single hiccup used to throw away an entire
multi-scene render. These helpers retry an operation with exponential backoff
and only give up after several attempts.
"""
import time


class RetryError(Exception):
    """Raised when an operation still fails after exhausting all retry attempts."""


def retry_call(
    fn,
    *,
    attempts: int = 3,
    base_delay: float = 2.0,
    backoff: float = 2.0,
    max_delay: float = 30.0,
    success=None,
    label: str = "operation",
    logger=print,
    sleep=time.sleep,
):
    """Call ``fn()`` repeatedly until it succeeds or attempts are exhausted.

    A call is considered failed if it raises, or if ``success(result)`` returns
    False (when a ``success`` predicate is given; otherwise a result is accepted
    unless it is ``None``).

    Args:
        fn: Zero-argument callable performing the work.
        attempts: Maximum number of tries (>= 1).
        base_delay: Seconds to wait before the second attempt.
        backoff: Multiplier applied to the delay after each failed attempt.
        max_delay: Upper bound on the delay between attempts.
        success: Optional predicate ``result -> bool`` deciding acceptance.
        label: Human-readable name used in log lines.
        logger: Callable used to report retries (defaults to ``print``).
        sleep: Injectable sleep function (so tests run instantly).

    Returns:
        The first accepted result of ``fn()``.

    Raises:
        RetryError: If every attempt fails. The underlying exception, if any,
            is chained via ``__cause__``.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            result = fn()
            ok = success(result) if success is not None else (result is not None)
            if ok:
                if attempt > 1:
                    logger(f"[retry] {label} succeeded on attempt {attempt}/{attempts}")
                return result
            last_exc = None
            logger(f"[retry] {label} attempt {attempt}/{attempts} returned an unsuccessful result")
        except Exception as e:  # noqa: BLE001 - we deliberately retry on any error
            last_exc = e
            logger(f"[retry] {label} attempt {attempt}/{attempts} raised: {e}")

        if attempt < attempts:
            delay = min(base_delay * (backoff ** (attempt - 1)), max_delay)
            logger(f"[retry] {label} backing off {delay:.1f}s before next attempt")
            sleep(delay)

    msg = f"{label} failed after {attempts} attempt(s)"
    if last_exc is not None:
        raise RetryError(msg) from last_exc
    raise RetryError(msg + " (no successful result)")
