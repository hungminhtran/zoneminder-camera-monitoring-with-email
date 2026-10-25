import monitor


def test_slot_truncates_to_the_interval():
    assert monitor.slot_for(1000.7, 60) == 960


def test_slot_is_idempotent():
    slot = monitor.slot_for(1000.7, 60)

    assert monitor.slot_for(slot, 60) == slot


def test_timestamps_inside_one_interval_share_a_slot():
    assert monitor.slot_for(961.0, 60) == monitor.slot_for(1019.9, 60) == 960


def test_slot_moves_to_the_next_interval():
    assert monitor.slot_for(1020.0, 60) == 1020
