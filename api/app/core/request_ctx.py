from contextvars import ContextVar, Token

_authorization: ContextVar[str | None] = ContextVar("authorization", default=None)


def set_authorization(value: str | None) -> Token[str | None]:
    return _authorization.set(value)


def reset_authorization(token: Token[str | None]) -> None:
    _authorization.reset(token)


def current_authorization() -> str | None:
    return _authorization.get()
