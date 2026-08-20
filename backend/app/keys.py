"""Audit signing keys (Ed25519).

Audit events, checkpoints, and export bundles are signed with an Ed25519 private
key. Verification needs only the public key, so an external auditor can check an
exported bundle without holding any secret that would let them forge one. This
is the property an HMAC cannot provide.

For development the keypair is derived deterministically from the master secret.
A production deployment loads the private key from a file or a key management
service and publishes only the public key.
"""
from __future__ import annotations

import hashlib
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .config import settings

_private: Ed25519PrivateKey | None = None


def _load_private() -> Ed25519PrivateKey:
    global _private
    if _private is not None:
        return _private
    path = os.environ.get("APP_AUDIT_KEY_FILE", "")
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            _private = serialization.load_pem_private_key(f.read(), password=None)
    else:
        seed = hashlib.sha256(b"audit-ed25519|" + settings.master_secret).digest()
        _private = Ed25519PrivateKey.from_private_bytes(seed)
    return _private


def public_key_hex() -> str:
    pub = _load_private().public_key()
    raw = pub.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return raw.hex()


def sign_audit(data: bytes) -> str:
    return _load_private().sign(data).hex()


def verify_audit(data: bytes, signature_hex: str, public_hex: str | None = None) -> bool:
    try:
        raw = bytes.fromhex(public_hex or public_key_hex())
        pub = Ed25519PublicKey.from_public_bytes(raw)
        pub.verify(bytes.fromhex(signature_hex), data)
        return True
    except Exception:
        return False


def reset_keys_for_tests() -> None:
    global _private
    _private = None
