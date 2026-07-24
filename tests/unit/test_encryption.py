from __future__ import annotations

import pytest

from minince.infrastructure.security.encryption import EncryptionManager
from minince.shared.exceptions import EncryptionError


class TestEncryptionManager:
    def test_encrypt_decrypt(self) -> None:
        manager = EncryptionManager()
        original = "my-secret-password-123"
        encrypted = manager.encrypt(original)
        decrypted = manager.decrypt(encrypted)
        assert decrypted == original
        assert encrypted != original

    def test_encrypt_returns_string(self) -> None:
        manager = EncryptionManager()
        result = manager.encrypt("test")
        assert isinstance(result, str)

    def test_decrypt_returns_string(self) -> None:
        manager = EncryptionManager()
        encrypted = manager.encrypt("test")
        result = manager.decrypt(encrypted)
        assert isinstance(result, str)

    def test_decrypt_invalid_token(self) -> None:
        manager = EncryptionManager()
        with pytest.raises(EncryptionError):
            manager.decrypt("invalid-token")

    def test_different_keys_produce_different_results(self) -> None:
        key1 = EncryptionManager.generate_key()
        key2 = EncryptionManager.generate_key()
        manager1 = EncryptionManager(key1)
        manager2 = EncryptionManager(key2)
        original = "test-data"
        encrypted1 = manager1.encrypt(original)
        with pytest.raises(EncryptionError):
            manager2.decrypt(encrypted1)

    def test_generate_key(self) -> None:
        key = EncryptionManager.generate_key()
        assert isinstance(key, str)
        assert len(key) > 0

    def test_generate_keys_are_unique(self) -> None:
        key1 = EncryptionManager.generate_key()
        key2 = EncryptionManager.generate_key()
        assert key1 != key2

    def test_empty_string(self) -> None:
        manager = EncryptionManager()
        encrypted = manager.encrypt("")
        decrypted = manager.decrypt(encrypted)
        assert decrypted == ""

    def test_unicode_string(self) -> None:
        manager = EncryptionManager()
        original = "密码测试🔐"
        encrypted = manager.encrypt(original)
        decrypted = manager.decrypt(encrypted)
        assert decrypted == original

    def test_special_characters(self) -> None:
        manager = EncryptionManager()
        original = 'p@$$w0rd!#%^&*()_+-=[]{}|;:\'",.<>/?'
        encrypted = manager.encrypt(original)
        decrypted = manager.decrypt(encrypted)
        assert decrypted == original
