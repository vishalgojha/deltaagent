import base64
import json
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.config import get_settings


class VaultError(Exception):
    pass


class CredentialVault:
    def __init__(self) -> None:
        raw_key = get_settings().encryption_key.encode("utf-8")
        if len(raw_key) == 32:
            self._key = raw_key
        else:
            try:
                decoded = base64.urlsafe_b64decode(raw_key)
            except Exception as exc:  # noqa: BLE001
                raise VaultError("Invalid ENCRYPTION_KEY format") from exc
            if len(decoded) != 32:
                raise VaultError("ENCRYPTION_KEY must be 32-byte raw or base64")
            self._key = decoded
        self._aes = AESGCM(self._key)

    def encrypt(self, payload: dict) -> str:
        nonce = os.urandom(12)
        data = json.dumps(payload).encode("utf-8")
        cipher = self._aes.encrypt(nonce, data, None)
        return base64.urlsafe_b64encode(nonce + cipher).decode("utf-8")

    def decrypt(self, token: str) -> dict:
        try:
            data = base64.urlsafe_b64decode(token.encode("utf-8"))
            nonce = data[:12]
            cipher = data[12:]
            plain = self._aes.decrypt(nonce, cipher, None)
            return json.loads(plain.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise VaultError("Unable to decrypt credentials") from exc
