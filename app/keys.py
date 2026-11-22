"""The tool's own RSA key pair and session secret.

Both are created on first run inside the data directory, readable only by the
service user. The public half is published at /.well-known/jwks.json; Moodle
fetches it to check the tool's signed requests (AGS token requests).
"""
import hashlib
import json
import os
import secrets
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _create_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


class ToolKeys:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)

        key_path = data_dir / "tool_private_key.pem"
        if not key_path.exists():
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            _create_private(key_path, key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ))
        self.private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)

        public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.private_key.public_key()))
        self.kid = hashlib.sha256((public_jwk["n"] + public_jwk["e"]).encode()).hexdigest()[:16]
        public_jwk.update(kid=self.kid, alg="RS256", use="sig")
        self.jwks = {"keys": [public_jwk]}

        secret_path = data_dir / "session_secret"
        if not secret_path.exists():
            _create_private(secret_path, secrets.token_hex(32).encode())
        self.session_secret = secret_path.read_text().strip()
