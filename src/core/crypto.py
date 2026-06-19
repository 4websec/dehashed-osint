import base64
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import String, TypeDecorator

_NONCE_BYTES = 12


class FieldCipher:
    """AES-256-GCM authenticated encryption for individual field values."""

    def __init__(self, b64_key: str) -> None:
        key = base64.b64decode(b64_key)
        if len(key) != 32:
            raise ValueError("ENCRYPTION_KEY must decode to 32 bytes")
        self._aesgcm = AESGCM(key)

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        ct = self._aesgcm.encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(nonce + ct).decode()

    def decrypt(self, token: str) -> str:
        blob = base64.b64decode(token)
        nonce, ct = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
        return self._aesgcm.decrypt(nonce, ct, None).decode()


class EncryptedString(TypeDecorator[str]):
    """Transparent column encryption. Cipher injected at engine setup."""

    impl = String
    cache_ok = True
    _cipher: FieldCipher | None = None

    @classmethod
    def configure(cls, cipher: FieldCipher) -> None:
        cls._cipher = cipher

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        assert self._cipher is not None, "EncryptedString.configure() not called"
        return self._cipher.encrypt(str(value))

    def process_result_value(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        assert self._cipher is not None, "EncryptedString.configure() not called"
        return self._cipher.decrypt(str(value))
