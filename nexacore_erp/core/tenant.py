# Simple tenant placeholder so your code is ready for multi-account later.
_current = "default"

def set_tenant(account_id: str | None):
    global _current
    _current = account_id or "default"

def id() -> str:
    return _current
