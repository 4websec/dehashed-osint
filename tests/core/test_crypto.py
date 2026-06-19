import base64
import os

import pytest

from src.core.crypto import FieldCipher

KEY = base64.b64encode(os.urandom(32)).decode()


def test_encrypt_decrypt_round_trip():
    cipher = FieldCipher(KEY)
    token = cipher.encrypt("hunter2")
    assert token != "hunter2"
    assert cipher.decrypt(token) == "hunter2"


def test_ciphertext_is_nondeterministic():
    cipher = FieldCipher(KEY)
    assert cipher.encrypt("x") != cipher.encrypt("x")  # random nonce


def test_decrypt_rejects_tampered_token():
    cipher = FieldCipher(KEY)
    token = cipher.encrypt("secret")
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    with pytest.raises(Exception):  # AES-GCM auth tag failure
        cipher.decrypt(tampered)
