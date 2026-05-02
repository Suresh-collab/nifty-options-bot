"""
Phase 4 — Encrypted API key storage (4.5).

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
The encryption key is stored in BROKER_ENCRYPTION_KEY env var (base64-url,
44 chars).  Generate a fresh key with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Per-install salt: an additional BROKER_SALT env var (any non-empty string).
The salt is prepended to the plaintext before encryption so two installs
using the same BROKER_ENCRYPTION_KEY produce different ciphertexts.

Round-trip guarantee:
    plaintext == decrypt(encrypt(plaintext, key, salt), key, salt)

The plaintext (e.g. KITE_ACCESS_TOKEN) is never written to disk or logged.
"""
from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken


def generate_key() -> str:
    """Generate a new Fernet key.  Store result in BROKER_ENCRYPTION_KEY."""
    return Fernet.generate_key().decode()


def encrypt(plaintext: str, key: str, salt: str = "") -> str:
    """
    Encrypt *plaintext* with the Fernet *key*.
    If *salt* is provided it is prepended to the plaintext before encryption
    so that the same plaintext produces different ciphertexts on different
    installs.
    Returns a URL-safe base64 string (the Fernet token).
    """
    salted = (salt + plaintext).encode()
    return Fernet(key.encode()).encrypt(salted).decode()


def decrypt(token: str, key: str, salt: str = "") -> str:
    """
    Decrypt *token* and strip the leading *salt* bytes.
    Raises cryptography.fernet.InvalidToken if the key is wrong or data tampered.
    """
    salted = Fernet(key.encode()).decrypt(token.encode()).decode()
    if salt and salted.startswith(salt):
        return salted[len(salt):]
    return salted


def is_valid_key(key: str) -> bool:
    """Return True if *key* is a valid 32-byte Fernet key (base64-url encoded)."""
    try:
        raw = base64.urlsafe_b64decode(key.encode())
        return len(raw) == 32
    except Exception:
        return False
