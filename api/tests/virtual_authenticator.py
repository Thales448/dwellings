import json
import struct
from hashlib import sha256

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import bytes_to_base64url


class VirtualAuthenticator:
    """Software passkey used by tests. It sets user-present and user-verified."""

    def __init__(self) -> None:
        self._key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = secrets_token()
        self.sign_count = 0

    def registration(self, *, challenge: str, origin: str, rp_id: str) -> dict[str, object]:
        self.sign_count = 0
        auth_data = self._auth_data(rp_id, attested=True)
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        client_data = _client_data("webauthn.create", challenge, origin)
        credential_id = bytes_to_base64url(self.credential_id)
        return {
            "id": credential_id,
            "rawId": credential_id,
            "type": "public-key",
            "authenticatorAttachment": "platform",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "attestationObject": bytes_to_base64url(attestation),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
        }

    def authentication(
        self,
        *,
        challenge: str,
        origin: str,
        rp_id: str,
        user_handle: bytes,
    ) -> dict[str, object]:
        self.sign_count += 1
        auth_data = self._auth_data(rp_id, attested=False)
        client_data = _client_data("webauthn.get", challenge, origin)
        signature = self._key.sign(
            auth_data + sha256(client_data).digest(),
            ec.ECDSA(hashes.SHA256()),
        )
        credential_id = bytes_to_base64url(self.credential_id)
        return {
            "id": credential_id,
            "rawId": credential_id,
            "type": "public-key",
            "authenticatorAttachment": "platform",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(signature),
                "userHandle": bytes_to_base64url(user_handle),
            },
            "clientExtensionResults": {},
        }

    def _auth_data(self, rp_id: str, *, attested: bool) -> bytes:
        flags = 0x01 | 0x04
        body = b""
        if attested:
            flags |= 0x40
            numbers = self._key.public_key().public_numbers()
            cose = cbor2.dumps(
                {
                    1: 2,
                    3: -7,
                    -1: 1,
                    -2: numbers.x.to_bytes(32, "big"),
                    -3: numbers.y.to_bytes(32, "big"),
                }
            )
            body = (
                bytes(16)
                + struct.pack(">H", len(self.credential_id))
                + self.credential_id
                + cose
            )
        counter = struct.pack(">I", self.sign_count)
        header = sha256(rp_id.encode()).digest() + bytes([flags]) + counter
        return header + body


def secrets_token() -> bytes:
    from secrets import token_bytes

    return token_bytes(32)


def _client_data(kind: str, challenge: str, origin: str) -> bytes:
    return json.dumps(
        {"type": kind, "challenge": challenge, "origin": origin, "crossOrigin": False},
        separators=(",", ":"),
    ).encode()
