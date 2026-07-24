import threading
from collections.abc import Callable
from typing import TypeVar

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError


_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)
MAX_PASSWORD_CHARACTERS = 256
MAX_PASSWORD_UTF8_BYTES = 512
PASSWORD_OPERATION_CONCURRENCY = 4
_PASSWORD_OPERATION_SLOTS = threading.BoundedSemaphore(PASSWORD_OPERATION_CONCURRENCY)
_Result = TypeVar("_Result")


class PasswordOperationBusy(RuntimeError):
    pass


def password_input_errors(password: str) -> list[str]:
    errors: list[str] = []
    if len(password) > MAX_PASSWORD_CHARACTERS:
        errors.append("password_too_long")
    if len(password.encode("utf-8")) > MAX_PASSWORD_UTF8_BYTES:
        errors.append("password_too_many_bytes")
    return errors


def validate_password_input(password: str) -> str:
    errors = password_input_errors(password)
    if errors:
        raise ValueError(",".join(errors))
    return password


def password_errors(password: str) -> list[str]:
    errors = password_input_errors(password)
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


def run_password_operation_bounded(
    operation: Callable[..., _Result], *args, **kwargs
) -> _Result:
    if not _PASSWORD_OPERATION_SLOTS.acquire(blocking=False):
        raise PasswordOperationBusy("Password operation capacity is busy")
    try:
        return operation(*args, **kwargs)
    finally:
        _PASSWORD_OPERATION_SLOTS.release()


def hash_password_bounded(password: str) -> str:
    return run_password_operation_bounded(hash_password, password)


def verify_password_bounded(password_hash: str, password: str) -> bool:
    return run_password_operation_bounded(verify_password, password_hash, password)


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
