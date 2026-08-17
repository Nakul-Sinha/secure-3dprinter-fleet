"""Content-addressed, encrypted blob storage.

Design files are envelope-encrypted and stored under a content id that is a hash
of the plaintext, so the id itself is an integrity check. Retrieval re-verifies
the hash, and AES-GCM authentication detects any tampering of the ciphertext.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .crypto import content_id, envelope_decrypt, envelope_encrypt, sha256_hex
from .models import Blob


class StorageError(Exception):
    pass


def put(session: Session, plaintext: bytes) -> tuple[str, str]:
    """Store ciphertext, return (cid, file_hash)."""
    ciphertext, nonce, wrapped = envelope_encrypt(plaintext)
    cid = content_id(plaintext)
    file_hash = sha256_hex(plaintext)
    if session.get(Blob, cid) is None:
        session.add(
            Blob(cid=cid, ciphertext=ciphertext, nonce=nonce, wrapped_key=wrapped, size=len(plaintext))
        )
        session.flush()
    return cid, file_hash


def get(session: Session, cid: str) -> bytes:
    blob = session.get(Blob, cid)
    if blob is None:
        raise StorageError(f"content not found: {cid}")
    try:
        plaintext = envelope_decrypt(blob.ciphertext, blob.nonce, blob.wrapped_key)
    except Exception as e:  # AES-GCM auth failure means tampering
        raise StorageError(f"integrity failure on decrypt: {e}") from e
    if content_id(plaintext) != cid:
        raise StorageError("content id mismatch (payload tampered)")
    return plaintext


def verify_on_receipt(session: Session, cid: str, expected_file_hash: str) -> bool:
    """Re-verify the payload hash before printing. Returns True if it matches."""
    try:
        plaintext = get(session, cid)
    except StorageError:
        return False
    return sha256_hex(plaintext) == expected_file_hash


def crypto_shred(session: Session, cid: str) -> bool:
    """Destroy the wrapped key by deleting the blob, making it unreadable."""
    blob = session.get(Blob, cid)
    if blob is None:
        return False
    session.delete(blob)
    session.flush()
    return True
