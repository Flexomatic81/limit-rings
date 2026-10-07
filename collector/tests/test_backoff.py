from limit_rings.sources import backoff

NOW = 1_791_300_000.0
MIN, MAX = backoff.MIN_PAUSE, backoff.MAX_PAUSE


def test_retry_after_in_seconds_and_as_http_date():
    assert backoff.retry_after("120", NOW) == 120
    assert backoff.retry_after(" 0 ", NOW) == 0
    # 1_791_300_000 = Tue, 06 Oct 2026 15:20:00 GMT
    assert backoff.retry_after("Tue, 06 Oct 2026 16:20:00 GMT", NOW) == 3600
    assert backoff.retry_after("Tue, 06 Oct 2026 14:20:00 GMT", NOW) == 0  # date in the past


def test_retry_after_ignores_missing_or_garbage():
    for value in (None, "", "soon", "-5", "1e9x", "Mon, 99 Foo 2026 00:00:00 GMT"):
        assert backoff.retry_after(value, NOW) is None


def test_fresh_state_is_not_blocked():
    assert backoff.blocked_until(backoff.new(), NOW) is None


def test_rate_limit_with_header_pauses_as_requested_within_bounds():
    for header, pause in (("1800", 1800), ("10", MIN), (str(10 * 3600), MAX)):
        state = backoff.new()
        backoff.record_rate_limit(state, NOW, header)
        assert backoff.blocked_until(state, NOW) == NOW + pause
        assert state["failures"] == 1


def test_rate_limit_without_header_grows_and_is_capped():
    state = backoff.new()
    pauses = []
    for _ in range(6):
        backoff.record_rate_limit(state, NOW, None)
        pauses.append(state["until"] - NOW)
    assert pauses == [600, 1200, 2400, 3600, 3600, 3600]


def test_success_clears_the_pause():
    state = backoff.new()
    backoff.record_rate_limit(state, NOW, None)
    backoff.record_success(state)
    assert state == backoff.new()
    assert backoff.blocked_until(state, NOW) is None


def test_pause_ends_and_clock_set_back_does_not_block_for_long():
    state = backoff.new()
    backoff.record_rate_limit(state, NOW, "600")
    assert backoff.blocked_until(state, NOW + 599) == NOW + 600
    assert backoff.blocked_until(state, NOW + 600) is None
    # clock set back far: a pause can never last longer than MAX_PAUSE from now
    assert backoff.blocked_until(state, NOW - 2 * MAX) is None


def test_is_rate_limit():
    assert backoff.is_rate_limit(429) and backoff.is_rate_limit(503)
    assert not backoff.is_rate_limit(401) and not backoff.is_rate_limit(500)
