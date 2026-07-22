from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError


_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)


def password_errors(password: str) -> list[str]:
    errors: list[str] = []
    if len(password) < 10:
        errors.append("password_too_short")
    groups = sum(
        (
            any(char.isupper() for char in password),
            any(char.islower() for char in password),
            any(char.isdigit() for char in password),
            any(not char.isalnum() for char in password),
        )
    )
    if groups < 3:
        errors.append("password_not_complex_enough")
    return errors


def hash_password(password: str) -> str:
    errors = password_errors(password)
    if errors:
        raise ValueError(",".join(errors))
    return _HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _HASHER.verify(password_hash, password)
    except (InvalidHashError, VerifyMismatchError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _HASHER.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
