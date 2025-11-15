from __future__ import annotations

import json
from typing import Any

import structlog
from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

logger = structlog.get_logger(__name__)


class EncryptionManager:
    """Manages field-level encryption using Fernet symmetric encryption."""

    def __init__(self, encryption_key: str | SecretStr) -> None:
        """
        Initialize encryption manager with a key.

        Args:
            encryption_key: Base64-encoded Fernet key or SecretStr
        """
        if isinstance(encryption_key, SecretStr):
            key_str = encryption_key.get_secret_value()
        else:
            key_str = encryption_key

        try:
            key_bytes = key_str.encode() if isinstance(key_str, str) else key_str
            self.cipher = Fernet(key_bytes)
        except Exception as exc:
            logger.exception("encryption_key_initialization_failed")
            raise ValueError("Invalid encryption key") from exc

    def encrypt(self, plaintext: str | bytes) -> str:
        """
        Encrypt plaintext value.

        Args:
            plaintext: String or bytes to encrypt

        Returns:
            Base64-encoded encrypted value
        """
        if isinstance(plaintext, str):
            plaintext = plaintext.encode()

        try:
            ciphertext = self.cipher.encrypt(plaintext)
            return ciphertext.decode()
        except Exception as exc:
            logger.exception("encryption_failed")
            raise ValueError("Encryption failed") from exc

    def decrypt(self, ciphertext: str | bytes) -> str:
        """
        Decrypt ciphertext value.

        Args:
            ciphertext: Base64-encoded encrypted value

        Returns:
            Decrypted plaintext string
        """
        if isinstance(ciphertext, str):
            ciphertext = ciphertext.encode()

        try:
            plaintext = self.cipher.decrypt(ciphertext)
            return plaintext.decode()
        except InvalidToken as exc:
            logger.exception("decryption_invalid_token")
            raise ValueError("Invalid or corrupted encrypted data") from exc
        except Exception as exc:
            logger.exception("decryption_failed")
            raise ValueError("Decryption failed") from exc

    def encrypt_json(self, obj: Any) -> str:
        """Serialize and encrypt a JSON object."""
        plaintext = json.dumps(obj)
        return self.encrypt(plaintext)

    def decrypt_json(self, ciphertext: str) -> Any:
        """Decrypt and deserialize a JSON object."""
        plaintext = self.decrypt(ciphertext)
        return json.loads(plaintext)


def generate_encryption_key() -> str:
    """Generate a new Fernet encryption key."""
    key = Fernet.generate_key()
    return key.decode()
