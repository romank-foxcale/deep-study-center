"""The learner's Anthropic API key (SPEC §25): kept in the operating system's credential store, never in the workspace.

Order: the ``ANTHROPIC_API_KEY`` environment variable (for developers), then the OS keychain (Windows Credential
Manager, macOS Keychain, Secret Service on Linux) through ``keyring``. The key is never returned to the UI and never
written to the database, logs or job folders.
"""

from __future__ import annotations

import os
import threading

SERVICE = "Deep Study Center"
ACCOUNT = "anthropic-api-key"
_lock = threading.Lock()
_cache: dict[str, str | None] = {}


def _read() -> str | None:
    try:
        import keyring
        return keyring.get_password(SERVICE, ACCOUNT)
    except Exception:  # noqa: BLE001 - no usable keychain: behave as if no key is stored
        return None


def _write(value: str | None) -> None:
    import keyring
    if value is None:
        try:
            keyring.delete_password(SERVICE, ACCOUNT)
        except Exception:  # noqa: BLE001 - nothing stored
            pass
    else:
        keyring.set_password(SERVICE, ACCOUNT, value)


def get() -> str | None:
    env = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if env:
        return env
    with _lock:
        if "key" not in _cache:  # the keychain is read once; set() and clear() update the cache
            _cache["key"] = _read()
        return _cache["key"]


def source() -> str | None:
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return "environment"
    return "keychain" if get() else None


def set_key(value: str) -> None:
    value = value.strip()
    if not value.startswith("sk-ant-") or len(value) < 30:
        raise ValueError("this does not look like an Anthropic API key (it starts with sk-ant-)")
    _write(value)
    with _lock:
        _cache["key"] = value


def clear() -> None:
    _write(None)
    with _lock:
        _cache["key"] = None


def status() -> dict:
    return {"set": get() is not None, "source": source()}
