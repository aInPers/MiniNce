from __future__ import annotations

from typing import Final

from cryptography.fernet import Fernet, InvalidToken

from minince.config import settings
from minince.shared.exceptions import EncryptionError


class EncryptionManager:
    def __init__(self, encryption_key: str | None = None) -> None:
        key = encryption_key or settings.encryption_key
        try:
            self._fernet: Final[Fernet] = Fernet(key.encode() if isinstance(key, str) else key)
        except (ValueError, TypeError) as e:
            raise EncryptionError(f"Invalid encryption key: {e}") from e

    def encrypt(self, plaintext: str) -> str:
        try:
            encrypted = self._fernet.encrypt(plaintext.encode())
            return encrypted.decode()
        except Exception as e:
            raise EncryptionError(f"Encryption failed: {e}") from e

    def decrypt(self, ciphertext: str) -> str:
        try:
            decrypted = self._fernet.decrypt(ciphertext.encode())
            return decrypted.decode()
        except InvalidToken as e:
            raise EncryptionError("Invalid or corrupted ciphertext") from e
        except Exception as e:
            raise EncryptionError(f"Decryption failed: {e}") from e

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode()


encryption_manager = EncryptionManager()
