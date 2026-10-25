import web


def test_correct_passphrase_is_allowed():
    assert web.check_passphrase("hunter2", "hunter2") is True


def test_wrong_passphrase_is_rejected():
    assert web.check_passphrase("hunter3", "hunter2") is False


def test_empty_given_is_rejected():
    assert web.check_passphrase("", "hunter2") is False


def test_empty_expected_is_rejected():
    assert web.check_passphrase("hunter2", "") is False


def test_both_empty_is_rejected():
    assert web.check_passphrase("", "") is False


def test_none_is_rejected():
    assert web.check_passphrase(None, "hunter2") is False
    assert web.check_passphrase("hunter2", None) is False


def test_substring_is_rejected():
    assert web.check_passphrase("hunter", "hunter2") is False


def test_case_sensitive():
    assert web.check_passphrase("Hunter2", "hunter2") is False
