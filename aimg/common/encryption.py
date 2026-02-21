import base64
import hashlib

from cryptography.fernet import Fernet


def _derive_fernet_key(key: str) -> bytes:
    digest = hashlib.sha256(key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_value(plaintext: str, key: str) -> str:
    f = Fernet(_derive_fernet_key(key))
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str, key: str) -> str:
    f = Fernet(_derive_fernet_key(key))
    return f.decrypt(ciphertext.encode()).decode()
