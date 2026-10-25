import monitor

NOW = 1_700_000_000.0
PARAMS = dict(threshold=18.0, min_samples=3, max_samples=3, backoff_h=[1, 2, 4, 8, 24])


def decide(samples, fps, *, next_at=0.0, step=0, now=NOW, **overrides):
    params = {**PARAMS, **overrides}
    return monitor.should_notify(samples, next_at, step, fps, now, **params)


def test_too_few_samples_gives_no_decision():
    decision = decide([], 5.0)

    assert decision.notify is False
    assert decision.samples == (5.0,)


def test_healthy_average_does_not_notify():
    decision = decide([20.0, 21.0], 22.0)

    assert decision.notify is False
    assert decision.avg == 21.0


def test_healthy_average_resets_backoff():
    decision = decide([25.0, 25.0], 25.0, next_at=NOW + 86400, step=4)

    assert decision.notify is False
    assert decision.next_at == 0.0
    assert decision.step == 0


def test_low_average_without_history_notifies():
    decision = decide([5.0, 5.0], 5.0)

    assert decision.notify is True
    assert decision.avg == 5.0


def test_quiet_before_next_at():
    decision = decide([5.0, 5.0], 5.0, next_at=NOW + 100, step=2)

    assert decision.notify is False
    assert decision.next_at == NOW + 100
    assert decision.step == 2


def test_notifies_when_next_at_is_due():
    decision = decide([5.0, 5.0], 5.0, next_at=NOW, step=1)

    assert decision.notify is True
    assert decision.next_at == NOW + 7200
    assert decision.step == 2


def test_average_equal_to_threshold_is_healthy():
    decision = decide([18.0, 18.0], 18.0)

    assert decision.avg == 18.0
    assert decision.notify is False


def test_zero_fps_counts_as_low():
    decision = decide([10.0, 10.0], 0.0)

    assert decision.notify is True


def test_window_keeps_only_the_last_samples():
    decision = decide([1.0, 2.0, 3.0, 4.0], 5.0, max_samples=2)

    assert decision.samples == (4.0, 5.0)


def test_samples_stay_in_chronological_order():
    decision = decide([1.0, 2.0], 3.0)

    assert decision.samples == (1.0, 2.0, 3.0)


def test_notify_only_happens_below_threshold():
    for fps in (0.0, 5.0, 18.0, 25.0):
        decision = decide([5.0, 5.0], fps)
        if decision.notify:
            assert decision.avg < 18.0
