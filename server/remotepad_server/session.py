"""Estado de pairing y de sesión activa (F-21, F-22)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

PAIR_TTL_SECONDS = 60.0
MAX_PAIR_ATTEMPTS = 5
LOCKOUT_SECONDS = 5 * 60.0
PING_TIMEOUT_SECONDS = 10.0


def generate_pin() -> str:
    """PIN aleatorio de 6 dígitos (puede empezar con 0)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def derive_token(pin: str, nonce_server: bytes, nonce_client: bytes) -> bytes:
    """token = HKDF-SHA256(ikm=pin, salt=nonce_s+nonce_c, info="remotepad-v1", len=32).

    32 bytes = un solo bloque de HKDF-Expand (RFC 5869): con L == tamaño de
    hash no hace falta iterar T(1), T(2)... alcanza con T(1).
    """
    salt = nonce_server + nonce_client
    prk = hmac.new(salt, pin.encode("utf-8"), hashlib.sha256).digest()
    okm = hmac.new(prk, b"remotepad-v1" + b"\x01", hashlib.sha256).digest()
    return okm


def compute_pair_proof(pin: str, nonce_server: bytes, nonce_client: bytes) -> bytes:
    """proof = HMAC-SHA256(pin_utf8, nonce_s + nonce_c)."""
    return hmac.new(pin.encode("utf-8"), nonce_server + nonce_client, hashlib.sha256).digest()


def compute_auth_sig(token: bytes, nonce_server: bytes, nonce_client: bytes) -> bytes:
    """sig del mensaje `auth` = HMAC-SHA256(token, nonce_s + nonce_c), hex completo (sin truncar)."""
    return hmac.new(token, nonce_server + nonce_client, hashlib.sha256).digest()


def compute_message_sig(token: bytes, session_id: str, msg_id: str, msg_type: str) -> str:
    """sig de mensajes post-auth = hex(HMAC-SHA256(token, session+id+t))[:16]."""
    payload = f"{session_id}{msg_id}{msg_type}".encode("utf-8")
    return hmac.new(token, payload, hashlib.sha256).hexdigest()[:16]


@dataclass
class PairingChallenge:
    """Pairing en curso para UNA conexión TCP (no hay client_id en pair_answer)."""

    client_id: str
    client_name: str
    pin: str
    nonce_server: bytes
    nonce_client: bytes
    created_at: float = field(default_factory=time.monotonic)

    def is_expired(self, now: Optional[float] = None) -> bool:
        now = now if now is not None else time.monotonic()
        return now - self.created_at > PAIR_TTL_SECONDS


@dataclass
class LockoutState:
    attempts: int = 0
    locked_until: Optional[float] = None

    def is_locked(self, now: Optional[float] = None) -> bool:
        now = now if now is not None else time.monotonic()
        return self.locked_until is not None and now < self.locked_until

    def register_failure(self, now: Optional[float] = None) -> None:
        now = now if now is not None else time.monotonic()
        self.attempts += 1
        if self.attempts >= MAX_PAIR_ATTEMPTS:
            self.locked_until = now + LOCKOUT_SECONDS
            self.attempts = 0

    def reset(self) -> None:
        self.attempts = 0
        self.locked_until = None


@dataclass
class ActiveSession:
    """Única sesión activa a la vez (F-22). `last_udp_seq` lo usa motion_server (S-09)."""

    session_id: str
    client_id: str
    token: bytes
    created_at: float = field(default_factory=time.monotonic)
    last_ping: float = field(default_factory=time.monotonic)
    last_udp_seq: Optional[int] = None
    natural_scroll: bool = True

    def touch_ping(self, now: Optional[float] = None) -> None:
        self.last_ping = now if now is not None else time.monotonic()

    def is_ping_stale(self, now: Optional[float] = None, timeout: float = PING_TIMEOUT_SECONDS) -> bool:
        now = now if now is not None else time.monotonic()
        return now - self.last_ping > timeout
