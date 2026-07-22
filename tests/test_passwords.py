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
