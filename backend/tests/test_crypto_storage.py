from app import crypto, storage
from app.models import Blob


def test_canonical_hash_is_stable():
    a = crypto.hash_obj({"b": 1, "a": 2})
    b = crypto.hash_obj({"a": 2, "b": 1})
    assert a == b


def test_envelope_roundtrip():
    pt = b"secret g-code payload"
    ct, nonce, wrapped = crypto.envelope_encrypt(pt)
    assert ct != pt
    assert crypto.envelope_decrypt(ct, nonce, wrapped) == pt


def test_content_id_is_integrity_check():
    assert crypto.content_id(b"x") != crypto.content_id(b"y")


def test_storage_put_get_roundtrip(session):
    pt = b"design-file-bytes"
    cid, file_hash = storage.put(session, pt)
    assert storage.get(session, cid) == pt
    assert storage.verify_on_receipt(session, cid, file_hash) is True


def test_storage_detects_tampering(session):
    cid, file_hash = storage.put(session, b"original")
    # tamper the stored ciphertext directly
    blob = session.get(Blob, cid)
    blob.ciphertext = blob.ciphertext[:-1] + bytes([blob.ciphertext[-1] ^ 0x01])
    session.flush()
    assert storage.verify_on_receipt(session, cid, file_hash) is False


def test_crypto_shred_makes_unreadable(session):
    cid, _ = storage.put(session, b"to-be-shredded")
    assert storage.crypto_shred(session, cid) is True
    try:
        storage.get(session, cid)
        assert False, "expected StorageError"
    except storage.StorageError:
        pass
