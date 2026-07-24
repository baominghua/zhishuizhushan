import threading
import time

import pytest

from server.modules import passwords
from server.modules.passwords import hash_password, needs_rehash, password_errors, verify_password


def test_password_policy_requires_length_and_three_character_groups():
    assert "password_too_short" in password_errors("Abc123!")
    assert "password_not_complex_enough" in password_errors("abcdefghij")
    assert password_errors("Bamboo-2026!") == []


def test_argon2_hash_round_trip_never_contains_plaintext():
    encoded = hash_password("Bamboo-2026!")
    assert encoded.startswith("$argon2id$")
    assert "Bamboo-2026!" not in encoded
    assert verify_password(encoded, "Bamboo-2026!") is True
    assert verify_password(encoded, "wrong-password") is False
    assert needs_rehash(encoded) is False


def test_hash_and_verify_share_a_nonblocking_global_operation_limit(monkeypatch):
    reached_limit = threading.Event()
    release = threading.Event()
    state_lock = threading.Lock()
    active = 0

    def held_hash(_password):
        nonlocal active
        with state_lock:
            active += 1
            if active == passwords.PASSWORD_OPERATION_CONCURRENCY:
                reached_limit.set()
        release.wait(timeout=2)
        with state_lock:
            active -= 1
        return "hash"

    monkeypatch.setattr(passwords, "hash_password", held_hash)
    workers = [
        threading.Thread(
            target=passwords.hash_password_bounded,
            args=(f"Bamboo-{index}-2026!",),
        )
        for index in range(passwords.PASSWORD_OPERATION_CONCURRENCY)
    ]
    for worker in workers:
        worker.start()
    assert reached_limit.wait(timeout=1)

    started = time.monotonic()
    with pytest.raises(passwords.PasswordOperationBusy):
        passwords.run_password_operation_bounded(lambda: True)
    elapsed = time.monotonic() - started

    release.set()
    for worker in workers:
        worker.join(timeout=1)
    assert elapsed < 0.1
