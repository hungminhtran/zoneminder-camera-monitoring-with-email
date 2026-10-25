import monitor

NOW = 1_700_000_000.0
PARAMS = dict(threshold=18.0, window_size=3, backoff_h=[1, 2, 4, 8, 24])


def ladder(count):
    samples, next_at, step = (5.0, 5.0), 0.0, 0
    now = NOW
    decisions = []
    for _ in range(count):
        decision = monitor.should_notify(samples, next_at, step, 5.0, now, **PARAMS)
        decisions.append(decision)
        samples, next_at, step = decision.samples, decision.next_at, decision.step
        now = decision.next_at
    return decisions


def test_first_alert_schedules_one_hour():
    decision = ladder(1)[0]

    assert decision.notify is True
    assert decision.next_at == NOW + 3600
    assert decision.step == 1


def test_second_alert_schedules_two_hours():
    first, second = ladder(2)

    assert second.notify is True
    assert second.next_at == first.next_at + 7200
    assert second.step == 2


def test_third_alert_schedules_four_hours():
    decisions = ladder(3)

    assert decisions[2].next_at == decisions[1].next_at + 14400
    assert decisions[2].step == 3


def test_fourth_alert_schedules_eight_hours():
    decisions = ladder(4)

    assert decisions[3].next_at == decisions[2].next_at + 28800
    assert decisions[3].step == 4


def test_fifth_alert_schedules_the_ceiling():
    decisions = ladder(5)

    assert decisions[4].next_at == decisions[3].next_at + 86400
    assert decisions[4].step == 4


def test_ceiling_holds_after_many_alerts():
    decisions = ladder(8)

    assert decisions[7].next_at == decisions[6].next_at + 86400
    assert decisions[7].step == 4


def test_healthy_sample_resets_the_ladder():
    first = ladder(1)[0]
    quiet = monitor.should_notify(first.samples, first.next_at, first.step, 30.0, NOW, **PARAMS)
    healthy = monitor.should_notify(
        quiet.samples, quiet.next_at, quiet.step, 30.0, NOW, **PARAMS
    )

    assert max(healthy.samples) > 18.0
    assert healthy.next_at == 0.0
    assert healthy.step == 0


def test_recovery_then_drop_needs_a_full_window_again():
    first = ladder(1)[0]
    recovered = monitor.should_notify(
        first.samples, first.next_at, first.step, 30.0, NOW, **PARAMS
    )

    samples, next_at, step = recovered.samples, 0.0, 0
    now = NOW
    decisions = []
    for _ in range(4):
        decision = monitor.should_notify(samples, next_at, step, 5.0, now, **PARAMS)
        decisions.append(decision)
        samples, next_at, step = decision.samples, decision.next_at, decision.step
        now += 60

    assert [decision.notify for decision in decisions] == [False, False, True, False]
    assert decisions[2].step == 1
    assert decisions[2].next_at == NOW + 120 + 3600


def test_now_far_past_next_at_alerts_once():
    decision = monitor.should_notify(
        (5.0, 5.0), NOW - 100000, 0, 5.0, NOW, **PARAMS
    )

    assert decision.notify is True
    assert decision.next_at == NOW + 3600


def test_next_at_passed_but_healthy_is_quiet_and_resets():
    decision = monitor.should_notify(
        (20.0, 20.0), NOW - 100000, 3, 20.0, NOW, **PARAMS
    )

    assert decision.notify is False
    assert decision.next_at == 0.0
    assert decision.step == 0
