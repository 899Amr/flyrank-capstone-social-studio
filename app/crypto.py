import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class TokenCipher:
    def __init__(self, encoded_key: str) -> None:
        key = base64.urlsafe_b64decode(encoded_key.encode())
        if len(key) != 32:
            raise ValueError("ENCRYPTION_KEY must encode exactly 32 bytes")
        self._cipher = AESGCM(key)

    def encrypt(self, plaintext: str) -> tuple[bytes, bytes]:
        nonce = os.urandom(12)
        return nonce, self._cipher.encrypt(nonce, plaintext.encode(), None)

    def decrypt(self, nonce: bytes, ciphertext: bytes) -> str:
        return self._cipher.decrypt(nonce, ciphertext, None).decode()


