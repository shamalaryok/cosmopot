from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from backend.security.encryption import EncryptionManager, generate_encryption_key


def test_generate_encryption_key() -> None:
    """Test that a valid Fernet key is generated."""
    key = generate_encryption_key()
    assert isinstance(key, str)
    assert len(key) > 0

    cipher = Fernet(key.encode())
    assert cipher is not None


def test_encryption_manager_initialization_with_string() -> None:
    """Test EncryptionManager initialization with string key."""
    key = generate_encryption_key()
    manager = EncryptionManager(key)
    assert manager.cipher is not None


def test_encryption_manager_initialization_with_secret_str() -> None:
    """Test EncryptionManager initialization with SecretStr."""
    key = generate_encryption_key()
    secret_key = SecretStr(key)
    manager = EncryptionManager(secret_key)
    assert manager.cipher is not None


def test_encryption_manager_initialization_with_invalid_key() -> None:
    """Test EncryptionManager initialization fails with invalid key."""
    with pytest.raises(ValueError, match="Invalid encryption key"):
        EncryptionManager("invalid-key")


def test_encrypt_decrypt_string() -> None:
    """Test encrypting and decrypting a string."""
    key = generate_encryption_key()
    manager = EncryptionManager(key)

    plaintext = "sensitive@email.com"
    ciphertext = manager.encrypt(plaintext)

    assert ciphertext != plaintext
    assert isinstance(ciphertext, str)

    decrypted = manager.decrypt(ciphertext)
    assert decrypted == plaintext


def test_encrypt_decrypt_bytes() -> None:
    """Test encrypting and decrypting bytes."""
    key = generate_encryption_key()
    manager = EncryptionManager(key)

    plaintext = b"sensitive data"
    ciphertext = manager.encrypt(plaintext)

    assert isinstance(ciphertext, str)

    decrypted = manager.decrypt(ciphertext)
    assert decrypted == plaintext.decode()


def test_encrypt_json_object() -> None:
    """Test encrypting and decrypting JSON objects."""
    key = generate_encryption_key()
    manager = EncryptionManager(key)

    data = {
        "email": "user@example.com",
        "card": "4111-1111-1111-1111",
        "nested": {"secret": "value"},
    }

    ciphertext = manager.encrypt_json(data)
    decrypted = manager.decrypt_json(ciphertext)

    assert decrypted == data


def test_different_keys_produce_different_ciphertexts() -> None:
    """Test that different keys produce different ciphertexts."""
    key1 = generate_encryption_key()
    key2 = generate_encryption_key()

    manager1 = EncryptionManager(key1)
    manager2 = EncryptionManager(key2)

    plaintext = "same plaintext"

    ciphertext1 = manager1.encrypt(plaintext)
    ciphertext2 = manager2.encrypt(plaintext)

    assert ciphertext1 != ciphertext2


def test_decrypt_with_wrong_key_fails() -> None:
    """Test that decryption with wrong key fails."""
    key1 = generate_encryption_key()
    key2 = generate_encryption_key()

    manager1 = EncryptionManager(key1)
    manager2 = EncryptionManager(key2)

    plaintext = "sensitive data"
    ciphertext = manager1.encrypt(plaintext)

    with pytest.raises(ValueError, match="Invalid or corrupted encrypted data"):
        manager2.decrypt(ciphertext)


def test_decrypt_corrupted_data_fails() -> None:
    """Test that decryption of corrupted data fails."""
    key = generate_encryption_key()
    manager = EncryptionManager(key)

    corrupted_ciphertext = "invalid base64!!!corrupted!!!"

    with pytest.raises(ValueError):
        manager.decrypt(corrupted_ciphertext)


def test_encrypt_empty_string() -> None:
    """Test encrypting and decrypting an empty string."""
    key = generate_encryption_key()
    manager = EncryptionManager(key)

    plaintext = ""
    ciphertext = manager.encrypt(plaintext)

    decrypted = manager.decrypt(ciphertext)
    assert decrypted == plaintext


def test_encrypt_large_string() -> None:
    """Test encrypting and decrypting a large string."""
    key = generate_encryption_key()
    manager = EncryptionManager(key)

    plaintext = "x" * 10000
    ciphertext = manager.encrypt(plaintext)

    decrypted = manager.decrypt(ciphertext)
    assert decrypted == plaintext


def test_multiple_keys_isolation() -> None:
    """Test that multiple keys maintain isolation."""
    key1 = generate_encryption_key()
    key2 = generate_encryption_key()

    manager1 = EncryptionManager(key1)
    manager2 = EncryptionManager(key2)

    plaintext1 = "data for key 1"
    plaintext2 = "data for key 2"

    ciphertext1 = manager1.encrypt(plaintext1)
    ciphertext2 = manager2.encrypt(plaintext2)

    assert manager1.decrypt(ciphertext1) == plaintext1
    assert manager2.decrypt(ciphertext2) == plaintext2

    with pytest.raises(ValueError):
        manager1.decrypt(ciphertext2)

    with pytest.raises(ValueError):
        manager2.decrypt(ciphertext1)
