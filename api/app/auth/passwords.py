from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.auth.breached import is_breached

hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=1)


class PasswordRejected(ValueError):
    pass


def validate_password(password: str) -> None:
    if len(password) < 12:
        raise PasswordRejected("password must be at least 12 characters")
    if is_breached(password):
        raise PasswordRejected("password is too common")


def hash_password(password: str) -> str:
    validate_password(password)
    return hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return bool(hasher.verify(password_hash, password))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


@lru_cache
def _dummy_hash() -> str:
    return hasher.hash("not-a-real-dwellings-password")


def dummy_verify(password: str) -> None:
    verify_password(_dummy_hash(), password)
