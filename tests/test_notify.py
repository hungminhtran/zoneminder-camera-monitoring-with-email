import monitor

NOW = 1_700_000_000.0
PARAMS = dict(threshold=18.0, window_size=3, backoff_h=[1, 2, 4, 8, 24])


def decide(samples, fps, *, next_at=0.0, step=0, now=NOW, **overrides):
    params = {**PARAMS, **overrides}
    return monitor.should_notify(samples, next_at, step, fps, now, **params)


def test_too_few_samples_gives_no_decision():
    decision = decide([], 5.0)

    assert decision.notify is False
    assert decision.samples == (5.0,)


def test_healthy_window_does_not_notify():
    decision = decide([20.0, 21.0], 22.0)

    assert decision.notify is False
    assert decision.avg == 21.0


def test_healthy_window_resets_backoff():
    decision = decide([25.0, 25.0], 25.0, next_at=NOW + 86400, step=4)

    assert decision.notify is False
    assert decision.next_at == 0.0
    assert decision.step == 0


def test_full_window_of_lows_notifies():
    decision = decide([5.0, 5.0], 5.0)

    assert decision.notify is True
    assert decision.avg == 5.0


def test_single_recovered_sample_prevents_notification():
    decision = decide([3.0, 3.0], 20.0)

    assert decision.notify is False
    assert decision.next_at == 0.0


def test_low_window_after_a_dip_needs_a_full_window():
    dipped = decide([20.0, 20.0], 2.0)
    still_low = decide(dipped.samples, 2.0)
    third = decide(still_low.samples, 2.0)

    assert dipped.notify is False
    assert still_low.notify is False
    assert third.notify is True


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


def test_sample_equal_to_threshold_counts_as_low():
    decision = decide([18.0, 18.0], 18.0)

    assert decision.avg == 18.0
    assert decision.notify is True


def test_zero_fps_counts_as_low():
    decision = decide([10.0, 10.0], 0.0)

    assert decision.notify is True


def test_window_keeps_only_the_last_samples():
    decision = decide([1.0, 2.0, 3.0, 4.0], 5.0, window_size=2)

    assert decision.samples == (4.0, 5.0)


def test_samples_stay_in_chronological_order():
    decision = decide([1.0, 2.0], 3.0)

    assert decision.samples == (1.0, 2.0, 3.0)


def test_notify_only_happens_when_every_sample_is_low():
    for fps in (0.0, 5.0, 18.0, 25.0):
        decision = decide([5.0, 5.0], fps)
        if decision.notify:
            assert max(decision.samples) <= 18.0
        else:
            assert max(decision.samples) > 18.0
