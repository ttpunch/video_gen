import pytest

from reliability import retry_call, RetryError

# A no-op sleep so tests don't actually wait for backoff.
NO_SLEEP = lambda _s: None
SILENT = lambda _m: None


def test_succeeds_on_first_try():
    calls = []
    result = retry_call(lambda: calls.append(1) or "ok", sleep=NO_SLEEP, logger=SILENT)
    assert result == "ok"
    assert len(calls) == 1


def test_retries_then_succeeds():
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise RuntimeError("transient")
        return "done"

    result = retry_call(flaky, attempts=5, sleep=NO_SLEEP, logger=SILENT)
    assert result == "done"
    assert state["n"] == 3


def test_gives_up_and_raises_with_cause():
    def always_fails():
        raise ValueError("boom")

    with pytest.raises(RetryError) as exc:
        retry_call(always_fails, attempts=3, sleep=NO_SLEEP, logger=SILENT)
    assert isinstance(exc.value.__cause__, ValueError)


def test_unsuccessful_result_is_retried_via_predicate():
    results = iter([None, None, "value"])
    out = retry_call(
        lambda: next(results),
        attempts=3,
        success=lambda r: r is not None,
        sleep=NO_SLEEP,
        logger=SILENT,
    )
    assert out == "value"


def test_none_result_without_predicate_is_a_failure():
    with pytest.raises(RetryError):
        retry_call(lambda: None, attempts=2, sleep=NO_SLEEP, logger=SILENT)


def test_backoff_delays_grow_exponentially():
    delays = []
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        raise RuntimeError("x")

    with pytest.raises(RetryError):
        retry_call(
            flaky,
            attempts=4,
            base_delay=1.0,
            backoff=2.0,
            sleep=lambda s: delays.append(s),
            logger=SILENT,
        )
    # 3 sleeps between 4 attempts: 1, 2, 4
    assert delays == [1.0, 2.0, 4.0]


def test_max_delay_caps_backoff():
    delays = []
    with pytest.raises(RetryError):
        retry_call(
            lambda: (_ for _ in ()).throw(RuntimeError("x")),
            attempts=5,
            base_delay=10.0,
            backoff=10.0,
            max_delay=15.0,
            sleep=lambda s: delays.append(s),
            logger=SILENT,
        )
    assert max(delays) <= 15.0


def test_invalid_attempts_rejected():
    with pytest.raises(ValueError):
        retry_call(lambda: "x", attempts=0)
