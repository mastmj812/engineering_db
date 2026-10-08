"""anduin login for the runner — log in ONCE, reuse the token.

`python -m dealintake login` (or `.\\di login`) asks for the email and the
password (hidden prompt), trades them for anduin's 30-day bearer token and
keeps ONLY the token in the Windows Credential Manager (via `keyring`), keyed
by the anduin URL. The password is never stored, logged or passed as an
argument. ANDUIN_EMAIL / ANDUIN_PASSWORD in the environment still win when set.
"""

from __future__ import annotations

import getpass
import json
from typing import Any

SERVICE = "dealintake-anduin"


def _keyring() -> Any:
    try:
        import keyring
    except ImportError as e:            # optional dependency: requirements-dealintake.txt
        raise RuntimeError("the `keyring` package is missing — pip install -r requirements-dealintake.txt") from e
    return keyring


def load(base_url: str) -> dict[str, Any] | None:
    """{token, email, display_name} saved by `login`, or None."""
    try:
        raw = _keyring().get_password(SERVICE, base_url)
    except RuntimeError:
        return None
    return json.loads(raw) if raw else None


def save(base_url: str, token: str, user: dict[str, Any]) -> None:
    _keyring().set_password(SERVICE, base_url, json.dumps({
        "token": token, "email": user.get("email"), "display_name": user.get("display_name"),
    }))


def interactive_login(client: Any) -> dict[str, Any]:
    """Prompt, log in, store the token. Returns the anduin user."""
    prev = load(client.base) or {}
    default = prev.get("email") or ""
    email = input(f"anduin email{f' [{default}]' if default else ''}: ").strip() or default
    pw = getpass.getpass("anduin password (hidden): ")
    r = client.request_token(email, pw)
    save(client.base, r["access_token"], r.get("user") or {"email": email})
    return r.get("user") or {"email": email}
