"""Cryptographic primitives: canonical hashing and envelope encryption.

Envelope encryption follows the design: a fresh per-payload data key (DEK)
encrypts the content with AES-256-GCM; the DEK is wrapped by a key-encryption
key (KEK). Destroying the wrapped DEK crypto-shreds the payload.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import settings


# ---- canonical hashing ----

def canonical_bytes(obj) -> bytes:
    """Deterministic serialization for hashing (sorted keys, no whitespace)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_obj(obj) -> str:
    return sha256_hex(canonical_bytes(obj))


def content_id(data: bytes) -> str:
    """Content address (a hash of the content, so the id is an integrity check)."""
    return "cid1-" + sha256_hex(data)


# ---- keyed signing (audit chain, sessions) ----

def hmac_sign(data: bytes, key: bytes | None = None) -> str:
    key = key or settings.session_secret
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def hmac_verify(data: bytes, signature: str, key: bytes | None = None) -> bool:
    return hmac.compare_digest(hmac_sign(data, key), signature)


# ---- envelope encryption ----

def _derive_kek() -> bytes:
    return hashlib.sha256(b"kek|" + settings.master_secret).digest()  # 32 bytes


def envelope_encrypt(plaintext: bytes) -> tuple[bytes, bytes, bytes]:
    """Return (ciphertext, nonce, wrapped_key)."""
    dek = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ciphertext = AESGCM(dek).encrypt(nonce, plaintext, None)

    kek = _derive_kek()
    knonce = os.urandom(12)
    wrapped = AESGCM(kek).encrypt(knonce, dek, None)
    return ciphertext, nonce, knonce + wrapped


def envelope_decrypt(ciphertext: bytes, nonce: bytes, wrapped_key: bytes) -> bytes:
    kek = _derive_kek()
    knonce, wrapped = wrapped_key[:12], wrapped_key[12:]
    dek = AESGCM(kek).decrypt(knonce, wrapped, None)
    return AESGCM(dek).decrypt(nonce, ciphertext, None)
