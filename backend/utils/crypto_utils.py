# Installed libraries
from cryptography.fernet import Fernet
import base64
import json
import os
from typing import Dict, Optional

integration_secret = os.getenv("ENVIRONMENT_SECRET")


def encrypt_string(string):
    # Generate a Fernet key from the integration_secret
    key = base64.urlsafe_b64encode(integration_secret.encode().ljust(32)[:32])
    f = Fernet(key)

    # Encrypt the string
    encrypted = f.encrypt(string.encode())

    return encrypted.decode()


def decrypt_string(encrypted_string):
    # Generate a Fernet key from the integration_secret
    key = base64.urlsafe_b64encode(integration_secret.encode().ljust(32)[:32])
    f = Fernet(key)

    # Decrypt the string
    decrypted = f.decrypt(encrypted_string.encode())

    return decrypted.decode()


def decrypt_connection_credentials(encrypted_credentials: str) -> Dict[str, Optional[str]]:
    """
    Decrypt all credential fields from a connection's encrypted_credentials JSON string.
    Returns a dict mapping each credential key to its decrypted value (or None on failure).
    """
    try:
        raw = json.loads(encrypted_credentials or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}

    if not isinstance(raw, dict):
        return {}

    decrypted: Dict[str, Optional[str]] = {}
    for key, enc_value in raw.items():
        if not enc_value:
            continue
        try:
            decrypted[key] = decrypt_string(enc_value)
        except Exception:
            decrypted[key] = None

    return decrypted
