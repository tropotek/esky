from contextvars import ContextVar, Token

_current: ContextVar[str] = ContextVar("esky_profile")


class NoProfileBound(Exception):
    """A tool ran outside a profile-scoped request."""


def set_profile(name: str) -> Token:
    return _current.set(name)


def reset_profile(token: Token) -> None:
    _current.reset(token)


def current_profile() -> str:
    try:
        return _current.get()
    except LookupError as exc:
        raise NoProfileBound() from exc
